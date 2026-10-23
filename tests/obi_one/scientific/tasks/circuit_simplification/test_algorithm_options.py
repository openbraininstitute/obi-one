"""Tests for algorithm options, neuron-set targeting, provenance and resource sizing."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.resource_estimation.circuit_simplification import (
    REDUCTION_ALGORITHMS,
    estimate_resources_for_algorithms,
)
from obi_one.core.info import Info
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.blocks.simplification_algorithms import metadata
from obi_one.scientific.blocks.simplification_algorithms.metadata import (
    ALGORITHM_EXPORT_DESCRIPTIONS,
    ALGORITHM_EXPORT_MAP,
    algorithm_supports_node_selection,
)
from obi_one.scientific.blocks.simplification_algorithms.models import (
    ALGORITHM_BLOCK_CLASSES,
    LifNestAlgorithm,
    NeuronReduceAlgorithm,
    SingleCompartmentAlgorithm,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.task import (
    PROVENANCE_FILE_NAME,
    CircuitSimplificationScanConfig,
    CircuitSimplificationTask,
)
from obi_one.scientific.unions_and_references.neuron_sets import BiophysicalNeuronSetReference

from .test_task import TestTaskExecution

TASK = "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask"


def _config_with_target_set(algorithms: dict) -> CircuitSimplificationScanConfig:
    return CircuitSimplificationScanConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=CircuitSimplificationScanConfig.Initialize(
            circuit=CircuitFromID(id_str="test-circuit-id"),
            target_neuron_set=BiophysicalNeuronSetReference(
                block_dict_name="neuron_sets", block_name="all_bio"
            ),
        ),
        neuron_sets={"all_bio": AllBiophysicalNeurons()},
        algorithms=algorithms,
    )


def _run(config, tmp_path: Path, mock_pipeline, *, target_set_name=None):
    task = CircuitSimplificationTask(config=config)
    mock_circuit = MagicMock(path=str(tmp_path / "input" / "circuit_config.json"))
    for name in config.algorithms:
        output = config.coordinate_output_root / name / "output"
        output.mkdir(parents=True, exist_ok=True)
        (output / "circuit_config.json").write_text("{}")
    with (
        patch(
            "obi_one.scientific.tasks.circuit_simplification.task.circuit_db_sdk.resolve_circuit",
            return_value=(mock_circuit, MagicMock()),
        ),
        patch(f"{TASK}._get_execution_activity", return_value=None),
        patch(f"{TASK}._resolve_target_neuron_set", return_value=target_set_name),
        patch(f"{TASK}._smoke_check_loadability"),
    ):
        task.execute(db_client=None)  # ty:ignore[invalid-argument-type]
    return mock_pipeline.call_args.kwargs


class TestAlgorithmBlocks:
    def test_neuron_reduce_registered_without_exporter(self):
        assert ALGORITHM_EXPORT_MAP["neuron_reduce"] == ("neuron_reduce", None)
        assert ALGORITHM_BLOCK_CLASSES["neuron_reduce"] is NeuronReduceAlgorithm

    def test_neat_reduction_not_exposed(self):
        """NEAT is held back until sonata-simplify packages its runner script."""
        assert "neat_reduction" not in ALGORITHM_EXPORT_MAP
        assert "neat_reduction" not in ALGORITHM_BLOCK_CLASSES
        assert "neat_reduction" not in ALGORITHM_EXPORT_DESCRIPTIONS

    def test_single_compartment_filter_defaults(self):
        assert SingleCompartmentAlgorithm().pipeline_kwargs() == {
            "filter_poles": 1,
            "filter_method": "timedomain",
            "strict_filters": True,
        }

    @pytest.mark.parametrize("poles", [0, 5])
    def test_filter_poles_out_of_range_rejected(self, poles):
        with pytest.raises(ValueError, match="filter_poles"):
            SingleCompartmentAlgorithm(filter_poles=poles)

    def test_filter_poles_can_be_scanned(self):
        assert SingleCompartmentAlgorithm(filter_poles=[1, 2, 4]).filter_poles == [1, 2, 4]

    def test_other_algorithms_use_pipeline_defaults(self):
        assert LifNestAlgorithm().pipeline_kwargs() == {}
        assert NeuronReduceAlgorithm().pipeline_kwargs() == {}

    def test_node_selection_support(self):
        assert algorithm_supports_node_selection("single_compartment")
        assert not algorithm_supports_node_selection("lif_nest")
        assert not algorithm_supports_node_selection("neuron_reduce")


class TestTargetNeuronSet:
    def test_target_set_accepted_for_single_compartment(self):
        config = _config_with_target_set({"sc": SingleCompartmentAlgorithm()})
        assert config.initialize.target_neuron_set is not None
        assert config.initialize.target_neuron_set.block_name == "all_bio"

    def test_target_set_rejected_for_unsupported_algorithm(self):
        with pytest.raises(ValueError, match="not supported by: lif_nest"):
            _config_with_target_set({"sc": SingleCompartmentAlgorithm(), "lif": LifNestAlgorithm()})

    def test_execute_passes_target_set_to_pipeline(
        self,
        mock_pipeline,
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        config = TestTaskExecution._make_config(tmp_path)
        config.initialize = CircuitSimplificationScanConfig.Initialize.model_construct(
            circuit=CircuitFromID(id_str="test-circuit-id"),
            target_neuron_set=MagicMock(),
        )
        kwargs = _run(config, tmp_path, mock_pipeline, target_set_name="MySet")
        sim_config = json.loads(Path(kwargs["simulation_config"]).read_text(encoding="utf-8"))
        assert sim_config["node_set"] == "MySet"
        assert sim_config["node_sets_file"].endswith("single_compartment/node_sets.json")


class TestExecuteOptions:
    def test_execute_forwards_filter_options(
        self,
        mock_pipeline,
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        config = TestTaskExecution._make_config(tmp_path)
        config.algorithms["single_compartment"] = SingleCompartmentAlgorithm(
            filter_poles=2, filter_method="impedance", strict_filters=False
        )
        kwargs = _run(config, tmp_path, mock_pipeline)
        assert kwargs["filter_poles"] == 2
        assert kwargs["filter_method"] == "impedance"
        assert kwargs["strict_filters"] is False

    def test_execute_writes_provenance(self, mock_pipeline, tmp_path: Path):
        config = TestTaskExecution._make_config(tmp_path, algorithm="neuron_reduce")
        kwargs = _run(config, tmp_path, mock_pipeline)
        assert kwargs["simplification_mode"] == "neuron_reduce"
        provenance_path = (
            config.coordinate_output_root / "neuron_reduce" / "output" / PROVENANCE_FILE_NAME
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        assert provenance["algorithm"] == "neuron_reduce"
        assert set(provenance["package_versions"]) == {
            "obi-one",
            "sonata-simplify",
            "bluecellulab",
        }

    def test_package_versions_in_registered_description(self, tmp_path: Path):
        task = CircuitSimplificationTask(config=TestTaskExecution._make_config(tmp_path))
        task.config.info = Info(campaign_name="test", campaign_description="descr")
        task._circuit_entity = MagicMock()
        circuit_path = tmp_path / "circuit_config.json"
        circuit_path.write_text("{}")
        versions = {"obi-one": "0.0.0", "sonata-simplify": "0.0.0", "bluecellulab": "0.0.0"}
        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.circuit_registration.register_circuit",
            ) as register_circuit,
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.simplification_package_versions",
                return_value=versions,
            ),
        ):
            task._register_output(
                db_client=MagicMock(), circuit_path=circuit_path, algorithm_name="neuron_reduce"
            )
        kwargs = register_circuit.call_args.kwargs
        assert f"sonata-simplify {versions['sonata-simplify']}" in kwargs["description"]
        assert f"bluecellulab {versions['bluecellulab']}" in kwargs["description"]
        # Reduced-morphology outputs have no exporter and default to NEURON.
        assert kwargs["target_simulator"].name == "NEURON"


class TestResourceEstimation:
    def test_reduction_algorithms(self):
        assert {"neuron_reduce"} == REDUCTION_ALGORITHMS

    def test_reduction_needs_more_cores_than_point_neuron(self):
        point = estimate_resources_for_algorithms(["lif_nest"], nbio=10_000)
        reduction = estimate_resources_for_algorithms(["neuron_reduce"], nbio=10_000)
        assert reduction[0] > point[0]
        assert reduction[2] >= point[2]

    def test_time_adds_up_over_algorithms(self):
        _, _, single = estimate_resources_for_algorithms(["neuron_reduce"], nbio=100_000)
        _, _, both = estimate_resources_for_algorithms(
            ["neuron_reduce", "single_compartment"], nbio=100_000
        )
        assert both > single

    def test_small_circuit_uses_minimum_preset(self):
        assert estimate_resources_for_algorithms(["adex_brian2"], nbio=10) == (1, 4, 1)


def test_metadata_matches_sonata_simplify():
    """The static algorithm metadata matches the installed sonata-simplify."""
    algorithms = pytest.importorskip("sonata_simplify.algorithms")

    for base in {base for base, _ in metadata.ALGORITHM_EXPORT_MAP.values()}:
        assert metadata.BASE_ALGORITHM_TITLES[base] == algorithms.ALGORITHM_TITLES[base]
        assert metadata.BASE_ALGORITHM_DESCRIPTIONS[base] == algorithms.ALGORITHM_DESCRIPTIONS[base]
        supports = algorithms.get_algorithm_spec(base).capabilities.supports_node_selection
        assert (base in metadata.NODE_SELECTION_ALGORITHMS) == supports
