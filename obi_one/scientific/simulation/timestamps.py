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

    def timestamps(self):
        return [self.start_time + i * self.interval for i in range(self.number_of_repetitions)]


# class CategoricalTimestamps(Timestamps):
#     number_of_categories: int | list[int]
#     repetitions_per_category: int | list[int]
#     inter_trial_interval: float | list[float]

#     def timestamps(self):
#         timestamps = []
#         for i in range(self.number_of_categories):
#             category_start_time = self.start_time + i * (self.repetitions_per_category + self.inter_trial_interval)
#             timestamps.extend([category_start_time + j for j in range(self.repetitions_per_category)])
#         return timestamps
