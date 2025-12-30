from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)


class SimulationsForm(CircuitSimulationScanConfig):
    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize


class Simulation(CircuitSimulationSingleConfig):
    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize
