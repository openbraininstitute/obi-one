from typing_extensions import Literal
from obi_one.scientific.tasks.simulations import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulations import GenerateSimulationTask


class SimulationsForm(CircuitSimulationScanConfig):
    
    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize


class Simulation(CircuitSimulationSingleConfig):

    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize