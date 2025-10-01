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
