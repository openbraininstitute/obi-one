from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin


class SimulationExecutionSingleConfig(ScanConfig, SingleConfigMixin):
    pass


class CircuitSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class IonChannelModelSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class SingleNeuronSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class SingleNeuronSynaptomeSimulationExecutionSingleConfig(CircuitSimulationExecutionSingleConfig):
    pass
