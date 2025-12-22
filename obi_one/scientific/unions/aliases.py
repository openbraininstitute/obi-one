from typing import ClassVar

from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)


class SimulationsForm(CircuitSimulationScanConfig):
    class Config(CircuitSimulationScanConfig.Config):
        json_schema_extra: ClassVar[dict] = {
            "ui_enabled": True,
            "description": "SONATA simulation campaign",
        }


class Simulation(CircuitSimulationSingleConfig):
    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize
