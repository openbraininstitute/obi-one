from typing import ClassVar

from pydantic import ConfigDict

from obi_one.core.schema import SchemaKey
from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)


class SimulationsForm(CircuitSimulationScanConfig):
    """SONATA simulation campaign."""

    json_schema_extra_additions: ClassVar[dict] = {SchemaKey.UI_ENABLED: False}

    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize

    model_config = ConfigDict(
        json_schema_extra={SchemaKey.UI_ENABLED: False},
    )


class Simulation(CircuitSimulationSingleConfig):
    class Initialize(CircuitSimulationScanConfig.Initialize):
        pass

    initialize: Initialize
