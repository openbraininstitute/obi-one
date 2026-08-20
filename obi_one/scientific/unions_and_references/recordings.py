from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.recordings.ion_channel import IonChannelVariableRecording
from obi_one.scientific.blocks.recordings.soma import (
    SimulationDtSomaVoltageRecording,
    SimulationDtTimeWindowSomaVoltageRecording,
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

_SOMA_VOLTAGE_RECORDINGS = SomaVoltageRecording | TimeWindowSomaVoltageRecording

# Sampled on the simulation timestep, so these carry no Timestep parameter of their own.
_SIMULATION_DT_SOMA_VOLTAGE_RECORDINGS = (
    SimulationDtSomaVoltageRecording | SimulationDtTimeWindowSomaVoltageRecording
)


RecordingUnion = Annotated[_SOMA_VOLTAGE_RECORDINGS, Discriminator("type")]

Brian2RecordingUnion = Annotated[_SIMULATION_DT_SOMA_VOLTAGE_RECORDINGS, Discriminator("type")]

_RECORDINGS = IonChannelVariableRecording | _SOMA_VOLTAGE_RECORDINGS
IonChannelModelRecordingUnion = Annotated[
    _RECORDINGS,
    Discriminator("type"),
]

_ALL_RECORDINGS = _RECORDINGS | _SIMULATION_DT_SOMA_VOLTAGE_RECORDINGS


class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = IonChannelModelRecordingUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_ALL_RECORDINGS)
    }
