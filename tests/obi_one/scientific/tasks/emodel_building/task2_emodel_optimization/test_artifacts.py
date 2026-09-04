import json
from unittest.mock import Mock

import pytest
from bluepyemodel.preprocessing import (
    PARAMS_ARTIFACT_PATH,
    RECIPES_ARTIFACT_PATH,
    TASK2_ARTIFACT_CONTRACT_VERSION,
    TASK2_CONFIG_CONTRACT_VERSION,
    build_optimization_artifacts,
    normalize_ion_channel_model,
)
from entitysdk.types import TaskConfigType

from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.db_sdk import db_sdk
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    optimization_artifact_input_from_config,
)

from .test_parameter_selection import _model_entity, _scan_config_data


def test_artifact_bundle_has_versioned_relative_paths_and_writes_json(tmp_path):
    config = EModelOptimizationScanConfig.model_validate(_scan_config_data())
    normalized_models = {"icm-1": normalize_ion_channel_model(_model_entity())}

    artifacts = build_optimization_artifacts(
        optimization_artifact_input_from_config(
            config,
            mtype="L5PC",
            morphology_filename="morphology-1.swc",
        ),
        normalized_models,
    )
    artifacts.write(tmp_path)

    assert config.contract_version == TASK2_CONFIG_CONTRACT_VERSION
    assert artifacts.artifact_contract_version == TASK2_ARTIFACT_CONTRACT_VERSION
    assert artifacts.params_path == PARAMS_ARTIFACT_PATH
    assert artifacts.recipes_path == RECIPES_ARTIFACT_PATH
    assert (tmp_path / PARAMS_ARTIFACT_PATH).exists()
    assert (tmp_path / RECIPES_ARTIFACT_PATH).exists()
    assert (
        json.loads((tmp_path / RECIPES_ARTIFACT_PATH).read_text())["test"]["params"]
        == PARAMS_ARTIFACT_PATH
    )


def test_artifact_builder_rejects_unsupported_config_contract():
    config_data = _scan_config_data(contract_version="task2-config-v0")
    with pytest.raises(ValueError, match="contract_version"):
        EModelOptimizationScanConfig.model_validate(config_data)


def test_registered_single_config_serializes_versioned_contract(tmp_path, monkeypatch):
    config = EModelOptimizationScanConfig.model_validate(_scan_config_data())
    campaign = Mock(id="campaign-id")
    single = Mock(id="single-id")
    register = Mock(side_effect=[(campaign, Mock()), (single, Mock())])
    create_generation_activity = Mock()
    monkeypatch.setattr(db_sdk, "register_task_config_with_asset", register)
    monkeypatch.setattr(db_sdk, "create_generic_activity", create_generation_activity)

    grid_scan = GridScanGenerationTask(
        form=config,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    grid_scan.execute(db_client=Mock())

    coordinate = grid_scan.single_configs[0]
    serialized = json.loads(
        (coordinate.coordinate_output_root / "obi_one_coordinate.json").read_text()
    )
    assert serialized["contract_version"] == TASK2_CONFIG_CONTRACT_VERSION
    assert serialized["initialize"]["etype"]["id_str"] == "etype"

    assert register.call_count == 2
    campaign_call, single_call = register.call_args_list
    assert campaign_call.kwargs["task_config_type"] == TaskConfigType.emodel_optimization__campaign
    assert single_call.kwargs["task_config_type"] == TaskConfigType.emodel_optimization__config
    assert single_call.kwargs["task_config_generator_id"] == campaign.id
    create_generation_activity.assert_called_once()
