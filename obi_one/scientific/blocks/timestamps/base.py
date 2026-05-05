from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class Timestamps(Block, ABC):
    start_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Sart time of the timestamps in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def timestamps(self) -> list:
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self) -> list:
        pass

    def enumerate_non_negative_offset_timestamps(
        self, timestamp_offset: float
    ) -> Iterator[tuple[int, NonNegativeFloat]]:
        """Enumerate timestamp index and offset timestamps.

        Yields:
            Tuples of (timestamp_index, offset_timestamp)
        """
        for t_ind, timestamp in enumerate(self.timestamps()):
            offset_timestamp = timestamp + timestamp_offset
            if offset_timestamp < 0:
                msg = (
                    f"Invalid stimulus configuration: timestamp ({timestamp} ms) + "
                    f"timestamp_offset ({timestamp_offset} ms) must be >= 0."
                )
                raise ValueError(msg)

            yield t_ind, offset_timestamp
