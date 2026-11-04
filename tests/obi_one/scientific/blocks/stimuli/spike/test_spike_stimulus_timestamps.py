"""Cover SpikeStimulus default_timestamps Optional handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.blocks.stimuli.spike.fully_synchronous import FullySynchronousSpikeStimulus
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.unions_and_references.timestamps import TimestampsReference


def _timestamps_ref() -> TimestampsReference:
    ref = TimestampsReference(block_name="ts")
    ref.block = SingleTimestamp(start_time=10.0)
    return ref


@patch.object(SpikeStimulus, "_generate_config", return_value={"ok": True})
@patch.object(SpikeStimulus, "generate_spikes", return_value=Path("spikes.h5"))
@patch(
    "obi_one.scientific.blocks.stimuli.spike.base.resolve_neuron_set_ref_to_neuron_set",
)
def test_config_uses_builtin_default_timestamps_when_none(
    mock_resolve, mock_spikes, mock_cfg, tmp_path
):
    del mock_spikes, mock_cfg
    neuron_set = MagicMock()
    neuron_set.has_biophysical_neurons.return_value = True
    neuron_set.has_point_neurons.return_value = False
    mock_resolve.return_value = neuron_set
    stim = FullySynchronousSpikeStimulus()

    result = stim.config(
        circuit=MagicMock(),
        sonata_simulation_config_directory=tmp_path,
        simulation_length=100.0,
        default_timestamps=None,
    )

    assert isinstance(stim._default_timestamps, SingleTimestamp)
    assert stim._default_timestamps.start_time == pytest.approx(0.0)
    assert result == {"ok": True}


@patch.object(SpikeStimulus, "_generate_config", return_value={"ok": True})
@patch.object(SpikeStimulus, "generate_spikes", return_value=Path("spikes.h5"))
@patch(
    "obi_one.scientific.blocks.stimuli.spike.base.resolve_neuron_set_ref_to_neuron_set",
)
def test_config_keeps_provided_default_timestamps(mock_resolve, mock_spikes, mock_cfg, tmp_path):
    del mock_spikes, mock_cfg
    neuron_set = MagicMock()
    neuron_set.has_biophysical_neurons.return_value = True
    neuron_set.has_point_neurons.return_value = False
    mock_resolve.return_value = neuron_set
    provided = _timestamps_ref()
    stim = FullySynchronousSpikeStimulus()

    stim.config(
        circuit=MagicMock(),
        sonata_simulation_config_directory=tmp_path,
        simulation_length=100.0,
        default_timestamps=provided,
    )

    assert stim._default_timestamps is provided
