"""Tests for the ion channel fitting scan config."""

import re

import pytest
from entitysdk.types import AssetLabel
from pydantic import ValidationError

from obi_one.core.registry import task_registry
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.types import TaskType

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


def test_registration_names_the_asset_the_single_config_uploads():
    """`run_task_type` finds the config on the launched entity by this label, and the single
    config uploads it under the same one. A mismatch fails only on the executor.
    """
    label = task_registry.get_task_type_config_asset_label(TaskType.ion_channel_fitting)

    assert label == AssetLabel.ion_channel_modeling_generation_config
