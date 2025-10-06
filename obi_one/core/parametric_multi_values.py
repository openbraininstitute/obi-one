from typing import Self

import numpy as np
from pydantic import NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt, model_validator

from obi_one.core.base import OBIBaseModel


class ParametericMultiValue(OBIBaseModel):
    """Base class for parameteric multi-value types.

    These types define a range of values using parameters such as start, step, and end.
    """

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.start >= self.end:
            error = "start must be < end"
            raise ValueError(error)
        return self

    def __len__(self) -> int:
        """Length operator."""
        return len(self._values)


class IntRange(ParametericMultiValue):
    start: int
    step: PositiveInt
    end: int
    _values: list[int]

    @model_validator(mode="after")
    def generate_values(self) -> Self:
        self._values = list(range(self.start, self.end + 1, self.step))  # + 1 includes end in range
        return self

    def __ge__(self, v: int | None) -> bool:
        """Greater than or equal to operator."""
        if v is None:
            return True
        return all(_v >= v for _v in self._values)

    def __gt__(self, v: int | None) -> bool:
        """Greater than operator."""
        if v is None:
            return True
        return all(_v > v for _v in self._values)

    def __le__(self, v: int | None) -> bool:
        """Less than or equal to operator."""
        if v is None:
            return True
        return all(_v <= v for _v in self._values)

    def __lt__(self, v: int | None) -> bool:
        """Less than operator."""
        if v is None:
            return True
        return all(_v < v for _v in self._values)

    def __iter__(self) -> int:
        """Iterator."""
        return self._values.__iter__()


class FloatRange(ParametericMultiValue):
    start: float
    step: PositiveFloat
    end: float
    _values: list[float]

    @model_validator(mode="after")
    def generate_values(self) -> Self:
        n = round((self.end - self.start) / self.step)
        self._values = np.linspace(self.start, self.start + n * self.step, n + 1)

        # Round to avoid floating point precision issues
        decimals = len(str(self.step).split(".")[-1])
        self._values = np.round(self._values, decimals)

        if self._values[-1] > self.end:
            self._values = self._values[:-1]

        return self

    def __ge__(self, v: float | None) -> bool:
        """Greater than or equal to operator."""
        if v is None:
            return True
        return all(_v >= v for _v in self._values)

    def __gt__(self, v: float | None) -> bool:
        """Greater than operator."""
        if v is None:
            return True
        return all(_v > v for _v in self._values)

    def __le__(self, v: float | None) -> bool:
        """Less than or equal to operator."""
        if v is None:
            return True
        return all(_v <= v for _v in self._values)

    def __lt__(self, v: float | None) -> bool:
        """Less than operator."""
        if v is None:
            return True
        return all(_v < v for _v in self._values)

    def __iter__(self) -> float:
        """Iterator."""
        return self._values.__iter__()


class PositiveIntRange(IntRange):
    start: PositiveInt
    end: PositiveInt


class NonNegativeIntRange(IntRange):
    start: NonNegativeInt
    end: NonNegativeInt


class PositiveFloatRange(FloatRange):
    start: PositiveFloat
    end: PositiveFloat


class NonNegativeFloatRange(FloatRange):
    start: NonNegativeFloat
    end: NonNegativeFloat


"""
# This will fail
IntRange(start=0, step=0, end=10)

# OK
r = IntRange(start=0, step=1, end=10)

list(r)
>> [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

r > 3
False

len(r)


#### Using IntRange within another class with annotations

class Block(BaseModel):
    r: Annotated[IntRange, Field(ge=2, le=10, min_length=5)]

# This will fail
Block(r=IntRange(start=0, step=1, end=25))

# This will fail
Block(r=IntRange(start=2, step=5, end=20))

# OK
b = Block(r=IntRange(start=2, step=1, end=10))


#### Defining specific range types

p = PositiveIntRange(start=1, step=1, end=5)

n = NonNegativeIntRange(start=0, step=1, end=5)
"""
