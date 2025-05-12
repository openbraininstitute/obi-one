from abc import ABC, abstractmethod
from typing import Annotated

from pydantic import Field

from obi_one.core.block import Block


class Timestamps(Block, ABC):
    start_time: float | list[float]
    simulation_level_name: (
        None | Annotated[str, Field(min_length=1, description="Name within a simulation.")]
    ) = None

    def check_simulation_init(self):
        assert self.simulation_level_name is not None, (
            f"'{self.__class__.__name__}' initialization within a simulation required!"
        )

    @property
    def name(self):
        self.check_simulation_init()
        return self.simulation_level_name

    def timestamps(self):
        self.check_simulation_init()
        return self._resolve_timestamps()

    @abstractmethod
    def _resolve_timestamps(self):
        pass


class RegularTimestamps(Timestamps):
    number_of_repetitions: int | list[int]
    interval: float | list[float]

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]
