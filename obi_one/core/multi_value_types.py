from typing import Self

from core.base import OBIBaseModel
from pydantic import PositiveInt, model_validator


class IntRange(OBIBaseModel):
    start: int
    step: PositiveInt
    end: int
    _values: list[int]

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.start >= self.end:
            error = "start must be < end"
            raise ValueError(error)
        return self

    def __init__(self, *, start: int, step: PositiveInt, end: int) -> None:
        """Initialize IntRange and precompute values."""
        super().__init__(start=start, step=step, end=end)
        self._values = list(range(start, end + 1, step)) # + 1 includes end in range

    def __ge__(self, v: int) -> bool:
        """Greater than or equal to operator for IntRange."""
        return all(_v >= v for _v in self._values)

    def __gt__(self, v: int) -> bool:
        """Greater than operator for IntRange."""
        return all(_v > v for _v in self._values)

    def __le__(self, v: int) -> bool:
        """Less than or equal to operator for IntRange."""
        return all(_v <= v for _v in self._values)

    def __lt__(self, v: int) -> bool:
        """Less than operator for IntRange."""
        return all(_v < v for _v in self._values)

    def __len__(self) -> int:
        """Length operator for IntRange."""
        return len(self._values)

    def __iter__(self) -> int:
        """Iterator for IntRange."""
        return self._values.__iter__()


"""
# This will fail
IntRange(start=0, step=0, end=10)

# OK
r = IntRange(start=0, step=1, end=10)

list(r)
>> [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

r > 3
False (JI: Don't understand this)

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
class PositiveIntRange(IntRange):
    start: Annotated[int, Field(gt=0)]

p = PositiveIntRange(start=1, step=1, end=5)

class NonNegativeIntRange(IntRange):
    start: Annotated[int, Field(ge=0)]

n = NonNegativeIntRange(start=0, step=1, end=5)
"""
