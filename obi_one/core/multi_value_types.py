from typing import Literal, Self, TypedDict

from pydantic import BaseModel, field_validator, model_validator


class Step(BaseModel):
    type: Literal["step"]
    start: float
    end: float
    step: float

    @field_validator("step")
    @classmethod
    def step_positive(cls, v: float) -> float:
        if v <= 0.0:
            error = "step must be strictly positive"
            raise ValueError(error)
        return v

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.start >= self.end:
            error = "start must be < end when step is positive"
            raise ValueError(error)
        return self


class StepDict(TypedDict):
    type: Literal["step"]
    start: float
    end: float
    step: float


from pydantic import BaseModel, Field, PositiveInt
from typing import Annotated

class IntRange(BaseModel):
    start: int
    step: PositiveInt
    end: int
    _values: list[int]
    def __init__(self, *, start, step, end):
        super().__init__(start=start, step=step, end=end)
        self._values = list(range(start, end, step))
    def __ge__(self, v):
        return all(_v >= v for _v in self._values)
    def __gt__(self, v):
        return all(_v > v for _v in self._values)
    def __le__(self, v):
        return all(_v <= v for _v in self._values)
    def __lt__(self, v):
        return all(_v < v for _v in self._values)
    def __len__(self):
        return len(self._values)
    def __iter__(self):
        return self._values.__iter__()
