"""Tests for the ion channel fitting scan config."""

import re
from unittest.mock import Mock

import pytest
from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType
from pydantic import ValidationError

from obi_one.core.registry import task_registry
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig

ION_CHANNEL_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


def test_ion_channel_name_default_satisfies_its_own_pattern():
    """The default is pre-filled into the form, so a default that fails the field's own
    pattern blocks every user on first open with no obvious cause.
    """
    default = IonChannelFittingScanConfig.Initialize.model_fields["ion_channel_name"].default

    assert re.match(ION_CHANNEL_NAME_PATTERN, default), default


def test_ion_channel_name_rejects_a_name_neuron_could_not_use():
    """It becomes the NEURON SUFFIX, so it has to be a valid identifier."""
    with pytest.raises(ValidationError):
        IonChannelFittingScanConfig.Initialize(
            recordings=[{"id_str": "00000000-0000-0000-0000-000000000000"}],
            ion_channel_name="3 bad name",
        )


def test_recordings_are_kept_together_rather_than_scanned():
    """Several recordings are fitted into one model, so they are one tuple-valued
    parameter rather than a scan dimension that would split into one config each.
    """
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


def test_every_recording_is_an_input_of_the_task_config():
    """The campaign and each config list all recordings as inputs, so the platform can
    trace a fitted model back to every recording it was fitted to.
    """
    config = IonChannelFittingScanConfig.model_validate(
        {
            "info": {"campaign_name": "Kv3.1 fit", "campaign_description": "From traces."},
            "initialize": {
                "recordings": [
                    {"id_str": "00000000-0000-0000-0000-000000000001"},
                    {"id_str": "00000000-0000-0000-0000-000000000002"},
                ],
            },
            "model_type": {"type": "HodgkinHuxleyIonChannelModel"},
        }
    )
    db_client = Mock()
    db_client.get_entity.side_effect = lambda entity_id, **_: f"recording {entity_id}"

    assert config.input_entities(db_client=db_client) == [
        "recording 00000000-0000-0000-0000-000000000001",
        "recording 00000000-0000-0000-0000-000000000002",
    ]
