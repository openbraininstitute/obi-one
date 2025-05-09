from abc import ABC, abstractmethod

from obi_one.core.block import Block


class Timestamps(Block, ABC):
    start_time: float | list[float]

    @abstractmethod
    def timestamps(self):
        pass


class RegularTimestamps(Timestamps):
    number_of_repetitions: int | list[int]
    interval: float | list[float]

    def timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]
