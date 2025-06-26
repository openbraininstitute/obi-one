from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from obi_one.core.block import Block


class Timestamps(Block, ABC):
    start_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(default=0.0, description="Sart time of the timestamps in milliseconds (ms).", units="ms")
    ]

    def timestamps(self):
        self.check_simulation_init()
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self):
        pass


class SingleTimestamp(Timestamps):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."""

    title: ClassVar[str] = "Single Timestamp"

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time]


class RegularTimestamps(Timestamps):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."""

    title: ClassVar[str] = "Regular Timestamps"

    number_of_repetitions: Annotated[
        NonNegativeInt | list[NonNegativeInt], Field(default=10, description="Number of timestamps to generate.")
    ]
    interval: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(default=10.0, description="Interval between timestamps in milliseconds (ms).", units="ms")
    ]

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]
