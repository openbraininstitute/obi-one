from unittest.mock import Mock

import pytest
from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType
from pydantic import ValidationError

from obi_one.core.exception import ConfigValidationError
from obi_one.core.registry import task_registry
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.db_sdk import db_sdk
from obi_one.scientific.tasks.ion_channel_modeling import (
    HodgkinHuxleyIonChannelModel,
    IonChannelFittingScanConfig,
)


def test_ion_channel_name_default_satisfies_its_own_pattern():
    IonChannelFittingScanConfig.Initialize(
        recordings=[{"id_str": "00000000-0000-0000-0000-000000000000"}]
    )


def test_ion_channel_name_rejects_a_name_neuron_could_not_use():
    with pytest.raises(ValidationError):
        IonChannelFittingScanConfig.Initialize(
            recordings=[{"id_str": "00000000-0000-0000-0000-000000000000"}],
            ion_channel_name="3 bad name",
        )


def test_recordings_are_kept_together_rather_than_scanned():
    annotation = IonChannelFittingScanConfig.Initialize.model_fields["recordings"].annotation

    assert getattr(annotation, "__origin__", None) is tuple


def test_registration_uses_the_generic_ion_channel_modeling_task_entities():
    registration = task_registry.get_registration_for_scan_config(IonChannelFittingScanConfig)

    assert registration.asset_label == AssetLabel.task_config
    assert registration.campaign_task_config_type == TaskConfigType.ion_channel_modeling__campaign
    assert registration.single_task_config_type == TaskConfigType.ion_channel_modeling__config
    assert (
        registration.campaign_generation_task_activity_type
        == TaskActivityType.ion_channel_modeling__config_generation
    )
    assert (
        registration.single_task_activity_type == TaskActivityType.ion_channel_modeling__execution
    )


RECORDING_IDS = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]


def _db_client(temperatures=(25.0, 25.0)):
    db_client = Mock()
    by_id = dict(zip(RECORDING_IDS, temperatures, strict=True))
    db_client.get_entity.side_effect = lambda entity_id, **_: Mock(
        id=entity_id, temperature=by_id[entity_id]
    )
    return db_client


def _scan_config(**model_type):
    return IonChannelFittingScanConfig.model_validate(
        {
            "info": {"campaign_name": "Kv3.1 fit", "campaign_description": "From traces."},
            "initialize": {"recordings": [{"id_str": id_} for id_ in RECORDING_IDS]},
            "model_type": {"type": "HodgkinHuxleyIonChannelModel", **model_type},
        }
    )


def test_every_recording_is_an_input_of_the_task_config():
    recordings = _scan_config().input_entities(db_client=_db_client())

    assert [recording.id for recording in recordings] == RECORDING_IDS


def test_exponents_can_be_swept():
    model = HodgkinHuxleyIonChannelModel(m_power=[1, 2], h_power=[0, 4])

    assert model.m_power == [1, 2]
    assert model.h_power == [0, 4]


@pytest.mark.parametrize(
    "exponents",
    [{"m_power": 0}, {"m_power": [1, 5]}, {"h_power": -1}, {"h_power": [0, 5]}],
)
def test_exponents_out_of_range_are_rejected(exponents):
    with pytest.raises(ValidationError):
        HodgkinHuxleyIonChannelModel(**exponents)


def test_generate_registers_a_campaign_and_one_config_per_exponent(tmp_path, monkeypatch):
    task_configs = []
    activities = []

    def register_task_config_with_asset(**kwargs):
        task_configs.append(kwargs)
        return Mock(id=f"task config {len(task_configs)}"), Mock()

    monkeypatch.setattr(db_sdk, "register_task_config_with_asset", register_task_config_with_asset)
    monkeypatch.setattr(
        db_sdk, "create_generic_activity", lambda **kwargs: activities.append(kwargs)
    )
    GridScanGenerationTask(
        form=_scan_config(m_power=[1, 2]),
        output_root=tmp_path,
        coordinate_directory_option="ZERO_INDEX",
    ).execute(db_client=_db_client())

    campaign, *configs = task_configs
    assert campaign["task_config_type"] == TaskConfigType.ion_channel_modeling__campaign
    assert [r.id for r in campaign["input_entities"]] == RECORDING_IDS
    assert [c["task_config_type"] for c in configs] == [
        TaskConfigType.ion_channel_modeling__config
    ] * 2
    assert all([r.id for r in c["input_entities"]] == RECORDING_IDS for c in configs)
    assert all(c["task_config_generator_id"] == "task config 1" for c in configs)
    (generation,) = activities
    assert generation["activity_type"] == TaskActivityType.ion_channel_modeling__config_generation
    assert [c.id for c in generation["generated"]] == ["task config 2", "task config 3"]


def test_recordings_at_different_temperatures_are_rejected_even_when_one_is_unknown():
    with pytest.raises(ConfigValidationError, match="must share a temperature"):
        _scan_config().input_entities(db_client=_db_client(temperatures=(25.0, None)))


def test_generate_rejects_mixed_temperatures_before_registering_anything(tmp_path, monkeypatch):
    register = Mock()
    monkeypatch.setattr(db_sdk, "register_task_config_with_asset", register)

    with pytest.raises(ConfigValidationError):
        GridScanGenerationTask(
            form=_scan_config(),
            output_root=tmp_path,
            coordinate_directory_option="ZERO_INDEX",
        ).execute(db_client=_db_client(temperatures=(25.0, 34.0)))

    register.assert_not_called()
