from abc import ABC, abstractmethod
from pydantic import Field
from typing import Annotated

from obi_one.core.block import Block


class Timestamps(Block, ABC):
    start_time: float | list[float]
    sim_init_name: None | Annotated[str, Field(min_length=1, description="Name within a simulation.")] = None

    def check_sim_init(self):
        assert self.sim_init_name is not None, f"'{self.__class__.__name__}' initialization within a simulation required!"

    @property
    def name(self):
        self.check_sim_init()
        return self.sim_init_name

    def timestamps(self):
        self.check_sim_init()
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self):
        pass


class RegularTimestamps(Timestamps):
    number_of_repetitions: int | list[int]
    interval: float | list[float]

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]
