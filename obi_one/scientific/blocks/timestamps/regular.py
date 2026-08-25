from typing import ClassVar

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.timestamps.base import Timestamps


class RegularTimestamps(Timestamps):
    """A series of timestamps at regular intervals."""

    title: ClassVar[str] = "Regular Timestamps"

    interval: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=10.0,
        description="Interval between timestamps in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    number_of_repetitions: NonNegativeInt | list[NonNegativeInt] = Field(
        default=10,
        description="Number of timestamps to generate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]  # ty:ignore[invalid-argument-type, unsupported-operator]
