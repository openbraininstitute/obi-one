from abc import ABC, abstractmethod

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class Timestamps(Block, ABC):
    start_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Sart time of the timestamps in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: "ms",
        },
    )

    def timestamps(self) -> list:
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self) -> list:
        pass
