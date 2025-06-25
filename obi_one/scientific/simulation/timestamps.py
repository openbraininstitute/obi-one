from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.block import Block


class Timestamps(Block, ABC):
    start_time: float | list[float]

    def timestamps(self):
        self.check_simulation_init()
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self):
        pass


class SingleTimestamp(Timestamps):
    """Description to be added."""

    title: ClassVar[str] = "Single Timestamp"

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time]


class RegularTimestamps(Timestamps):
    """Description to be added."""

    title: ClassVar[str] = "Regular Timestamps"

    number_of_repetitions: int | list[int]
    interval: float | list[float]

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]
