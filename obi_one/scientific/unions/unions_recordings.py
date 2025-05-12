from obi_one.scientific.simulation.recording import (
    ExtraceullarLocationSetVoltageRecording,
    IntracellularLocationSetVoltageRecording,
    VoltageRecording,
)

RecordingUnion = (
    VoltageRecording
    | IntracellularLocationSetVoltageRecording
    | ExtraceullarLocationSetVoltageRecording
)
