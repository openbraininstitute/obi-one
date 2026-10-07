"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.recordings import (
    Annotated,
    Any,
    BlockReference,
    Brian2RecordingUnion,
    ClassVar,
    Discriminator,
    IonChannelModelRecordingUnion,
    IonChannelVariableRecording,
    MorphologyLocationVoltageRecording,
    RecordingReference,
    RecordingUnion,
    SimulationDtSomaVoltageRecording,
    SimulationDtTimeWindowSomaVoltageRecording,
    SomaVoltageRecording,
    TimeWindowMorphologyLocationVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

from obi_one_lazy.scientific.unions_and_references.recordings import (
    _ALL_RECORDINGS,
    _AllRecordingsUnion,
    _MORPHOLOGY_LOCATION_VOLTAGE_RECORDINGS,
    _RECORDINGS,
    _SIMULATION_DT_SOMA_VOLTAGE_RECORDINGS,
    _SOMA_VOLTAGE_RECORDINGS,
    _VOLTAGE_RECORDINGS,
)

__all__ = [
    "Annotated",
    "Any",
    "BlockReference",
    "Brian2RecordingUnion",
    "ClassVar",
    "Discriminator",
    "IonChannelModelRecordingUnion",
    "IonChannelVariableRecording",
    "MorphologyLocationVoltageRecording",
    "RecordingReference",
    "RecordingUnion",
    "SimulationDtSomaVoltageRecording",
    "SimulationDtTimeWindowSomaVoltageRecording",
    "SomaVoltageRecording",
    "TimeWindowMorphologyLocationVoltageRecording",
    "TimeWindowSomaVoltageRecording",
    "_ALL_RECORDINGS",
    "_AllRecordingsUnion",
    "_MORPHOLOGY_LOCATION_VOLTAGE_RECORDINGS",
    "_RECORDINGS",
    "_SIMULATION_DT_SOMA_VOLTAGE_RECORDINGS",
    "_SOMA_VOLTAGE_RECORDINGS",
    "_VOLTAGE_RECORDINGS",
]
