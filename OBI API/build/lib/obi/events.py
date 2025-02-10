from .multi_template import MultiTemplate

class Events(MultiTemplate):
    start_time: float | list[float]
    repetitions: int | list[int]
    iti: float | list[float]