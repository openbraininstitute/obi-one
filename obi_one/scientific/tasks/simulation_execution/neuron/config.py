from obi_one.scientific.tasks.simulation_execution.config import SimulationExecutionSingleConfig


class CircuitSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class IonChannelModelSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class SingleNeuronSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class SingleNeuronSynaptomeSimulationExecutionSingleConfig(CircuitSimulationExecutionSingleConfig):
    pass
