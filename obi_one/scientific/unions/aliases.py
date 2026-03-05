from typing import ClassVar

from pydantic import ConfigDict

from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)


class SimulationsForm(CircuitSimulationScanConfig):
    """SONATA simulation campaign."""

    json_schema_extra_additions: ClassVar[dict] = {"ui_enabled": False}

    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize

    model_config = ConfigDict(
        json_schema_extra={"ui_enabled": False},
    )


class Simulation(CircuitSimulationSingleConfig):
    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize
