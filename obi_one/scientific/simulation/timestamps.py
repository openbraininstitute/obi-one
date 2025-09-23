from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from obi_one.core.block import Block


class Timestamps(Block, ABC):
    start_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat],
        Field(
            default=0.0, description="Sart time of the timestamps in milliseconds (ms).", units="ms"
        ),
    ]

    def timestamps(self) -> list:
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self) -> list:
        pass


class SingleTimestamp(Timestamps):
    """A single timestamp at a specified time."""

    title: ClassVar[str] = "Single Timestamp"

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time]


class RegularTimestamps(Timestamps):
    """A series of timestamps at regular intervals."""

    title: ClassVar[str] = "Regular Timestamps"

    interval: Annotated[
        NonNegativeFloat | list[NonNegativeFloat],
        Field(
            default=10.0,
            description="Interval between timestamps in milliseconds (ms).",
            units="ms",
        ),
    ]

    number_of_repetitions: Annotated[
        NonNegativeInt | list[NonNegativeInt],
        Field(default=10, description="Number of timestamps to generate."),
    ]

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]
