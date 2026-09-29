import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import emodel_optimization as test_module
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import estimate


def _json_model() -> TaskLaunchSubmit:
    return TaskLaunchSubmit(task_type=TaskType.emodel_optimization, config_id=uuid4())


def _task_definition():
    return TASK_DEFINITIONS[TaskType.emodel_optimization]


def _single_config(
    offspring_size=5,
    max_ngen=20,
    optimisation_timeout=300.0,
):
    return SimpleNamespace(
        optimization_params=SimpleNamespace(offspring_size=offspring_size),
        optimization_settings=SimpleNamespace(
            max_ngen=max_ngen,
            optimisation_timeout=optimisation_timeout,
        ),
    )


def _patch_config(config=None, n_protocols=10, n_compartments=500):
    return (
        patch.object(
            test_module,
            "load_optimization_single_config",
            return_value=config or _single_config(),
        ),
        patch.object(test_module, "count_feature_protocols", return_value=n_protocols),
        patch.object(test_module, "count_morphology_compartments", return_value=n_compartments),
    )


class TestEstimateOptimizationWorkload:
    def test_floor_for_small_jobs(self):
        workload = estimate.estimate_optimization_workload(
            offspring_size=5, max_ngen=1, n_protocols=1, n_compartments=10
        )
        assert workload.timelimit_seconds == estimate.DEFAULT_TIMELIMIT_S
        assert workload.timelimit == "02:00"
        assert workload.used_cores == 5
        assert workload.n_waves == 1

    def test_used_cores_capped_by_offspring(self):
        workload = estimate.estimate_optimization_workload(
            offspring_size=5, max_ngen=20, n_protocols=10, n_compartments=500
        )
        assert workload.used_cores == 5

    def test_used_cores_capped_by_instance(self):
        workload = estimate.estimate_optimization_workload(
            offspring_size=200, max_ngen=20, n_protocols=10, n_compartments=500
        )
        assert workload.used_cores == estimate.CORES_PER_INSTANCE
        assert workload.n_waves == 3  # ceil(200 / 96)

    def test_scales_with_generations_and_protocols(self):
        small = estimate.estimate_optimization_workload(
            offspring_size=5, max_ngen=10, n_protocols=10, n_compartments=500
        )
        large = estimate.estimate_optimization_workload(
            offspring_size=5, max_ngen=100, n_protocols=40, n_compartments=500
        )
        assert large.wall_seconds > small.wall_seconds

    def test_optimisation_timeout_caps_evaluation_time(self):
        workload = estimate.estimate_optimization_workload(
            offspring_size=5,
            max_ngen=20,
            n_protocols=100,
            n_compartments=100_000,
            optimisation_timeout=10.0,
        )
        # Per-evaluation time is capped at the timeout even with a huge morphology.
        expected_wall = estimate.OVERHEAD_S + 21 * 10.0
        assert workload.wall_seconds == expected_wall

    def test_oversized_jobs_raise(self):
        with pytest.raises(ValueError, match="exceeds the maximum timelimit"):
            estimate.estimate_optimization_workload(
                offspring_size=200,
                max_ngen=10_000,
                n_protocols=100,
                n_compartments=1000,
            )

    def test_count_is_core_hours(self):
        workload = estimate.estimate_optimization_workload(
            offspring_size=5, max_ngen=1, n_protocols=1, n_compartments=10
        )
        assert workload.count == 5 * 2  # 5 cores x 2 h floored timelimit

    def test_count_minimum_one(self):
        workload = estimate.OptimizationWorkload(
            used_cores=1, n_waves=1, wall_seconds=10.0, timelimit_seconds=60.0
        )
        assert workload.count == 1


class TestCountFeatureProtocols:
    def _db_client_with_features(self, features):
        db_client = Mock()
        db_client.download_content.return_value = json.dumps(features).encode("utf-8")
        config = SimpleNamespace(
            initialize=SimpleNamespace(
                target_efeatures=SimpleNamespace(
                    entity=Mock(return_value=SimpleNamespace(id=uuid4()))
                )
            )
        )
        return db_client, config

    def test_counts_protocols_dict(self):
        features = {
            "emodel_a": {
                "fitness_calculator_configuration": {
                    "protocols": {"Step1": {}, "Step2": {}, "IDRest": {}}
                }
            }
        }
        db_client, config = self._db_client_with_features(features)
        with patch.object(
            estimate.db_sdk, "get_entity_asset_by_label", return_value=SimpleNamespace(id=uuid4())
        ):
            assert estimate.count_feature_protocols(db_client=db_client, config=config) == 3

    def test_falls_back_to_efeatures_keys(self):
        features = {
            "emodel_a": {
                "fitness_calculator_configuration": {
                    "efeatures": {
                        "Step1.soma.v.mean": {},
                        "Step1.soma.v.steady": {},
                        "IDRest.soma.v.mean": {},
                    }
                }
            }
        }
        db_client, config = self._db_client_with_features(features)
        with patch.object(
            estimate.db_sdk, "get_entity_asset_by_label", return_value=SimpleNamespace(id=uuid4())
        ):
            assert estimate.count_feature_protocols(db_client=db_client, config=config) == 2

    def test_empty_features_raise(self):
        db_client, config = self._db_client_with_features({"emodel_a": {}})
        with (
            patch.object(
                estimate.db_sdk,
                "get_entity_asset_by_label",
                return_value=SimpleNamespace(id=uuid4()),
            ),
            pytest.raises(ValueError, match="contains no protocols"),
        ):
            estimate.count_feature_protocols(db_client=db_client, config=config)


class TestCountMorphologyCompartments:
    def test_counts_swc_point_lines(self):
        swc = "# comment\n1 1 0 0 1 1 -1\n2 3 1 0 0.5 1\n\n3 3 2 0 0.5 1\n"
        config = SimpleNamespace(
            initialize=SimpleNamespace(
                morphology=SimpleNamespace(swc_file_content=Mock(return_value=swc))
            )
        )
        assert estimate.count_morphology_compartments(db_client=Mock(), config=config) == 3


class TestEstimateTaskResources:
    def test_returns_cluster_resources_with_timelimit(self):
        p_config, p_protocols, p_morph = _patch_config()
        with p_config, p_protocols, p_morph:
            result = test_module.estimate_task_resources(
                json_model=_json_model(),
                db_client=Mock(),
                task_definition=_task_definition(),
                compute_cell="cell_a",
            )
        assert result.type == "cluster"
        assert result.instances == 1
        assert result.instance_type == "large"
        assert result.compute_cell == "cell_a"
        assert result.timelimit == "02:00"  # small config hits the floor

    def test_larger_timelimit_for_bigger_workloads(self):
        p_config, p_protocols, p_morph = _patch_config(
            config=_single_config(offspring_size=200, max_ngen=50),
            n_protocols=20,
            n_compartments=5000,
        )
        with p_config, p_protocols, p_morph:
            result = test_module.estimate_task_resources(
                json_model=_json_model(),
                db_client=Mock(),
                task_definition=_task_definition(),
                compute_cell="cell_a",
            )
        hours, minutes = (int(x) for x in result.timelimit.split(":"))
        assert hours > 2 or (hours == 2 and minutes > 0)

    def test_oversized_job_raises_api_error(self):
        p_config, p_protocols, p_morph = _patch_config(
            config=_single_config(offspring_size=200, max_ngen=100_000),
            n_protocols=100,
            n_compartments=1000,
        )
        with (
            p_config,
            p_protocols,
            p_morph,
            pytest.raises(ApiError) as exc_info,
        ):
            test_module.estimate_task_resources(
                json_model=_json_model(),
                db_client=Mock(),
                task_definition=_task_definition(),
                compute_cell="cell_a",
            )
        assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
