import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import Field, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
)


class LearningEngineSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for learning engine-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.LearningEngine
    _timestep: ClassVar[PositiveFloat] = 0.1

    class Initialize(BaseSimulationScanConfig.Initialize):
        random_seed: int | list[int] = Field(
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
                SchemaKey.UI_HIDDEN: True,
            },
        )
