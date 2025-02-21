from ..core.template import Block

class Timestamps(Block):
    start_time: float | list[float]
    
class RegularTimestamps(Timestamps):
    number_of_repetitions: int | list[int]
    interval: float | list[float]
    
# class PoissonianTimestamps(Timestamps):

class CategoricalTimestamps(Timestamps):
    number_of_categories: int | list[int]
    repetitions_per_category: int | list[int]
    inter_trial_interval: float | list[float]


    
