import abc
from typing import Annotated, ClassVar

from libsonata import SimulatorType
from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.constants import (
    DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
)


class LearningEngineSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for learning engine-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.LearningEngine

    class Initialize(BaseSimulationScanConfig.Initialize):
        timestep: ClassVar[PositiveFloat] = 0.1

        simulation_length: (
            Annotated[
                NonNegativeFloat,
                Field(ge=MIN_SIMULATION_LENGTH_MILLISECONDS, le=MAX_SIMULATION_LENGTH_MILLISECONDS),
            ]
            | Annotated[
                list[
                    Annotated[
                        NonNegativeFloat,
                        Field(
                            ge=MIN_SIMULATION_LENGTH_MILLISECONDS,
                            le=MAX_SIMULATION_LENGTH_MILLISECONDS,
                        ),
                    ]
                ],
                Field(min_length=1),
            ]
        ) = Field(
            default=DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLISECONDS,
            },
        )
        v_init: float | list[float] = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLIVOLTS,
            },
        )
        random_seed: int | list[int] = Field(
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
                SchemaKey.UI_HIDDEN: True,
            },
        )

    def base_sonata_config(self, sonata_config: dict | None = None) -> dict:
        """Returns the base SONATA configuration for the simulation campaign."""
        sonata_config = super().base_sonata_config(sonata_config)
        return sonata_config
