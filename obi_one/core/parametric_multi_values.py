from typing import Annotated, Self

import numpy as np
from pydantic import (
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from obi_one.core.base import OBIBaseModel
from obi_one.core.exception import OBIONEError


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


NonNegativeFloatUnion = NonNegativeFloat | list[NonNegativeFloat] | NonNegativeFloatRange


def check_annotation_arguments_and_create_kwargs(ge: type, gt: type, le: type, lt: type) -> dict:
    """Check that only one of ge/gt and le/lt are provided and create Field kwargs."""
    field_kwargs = {}

    if ge and gt:
        msg = "Only one of ge or gt can be provided."
        raise OBIONEError(msg)
    if le and lt:
        msg = "Only one of le or lt can be provided."
        raise OBIONEError(msg)

    if ge is not None:
        field_kwargs["ge"] = ge
    if gt is not None:
        field_kwargs["gt"] = gt
    if le is not None:
        field_kwargs["le"] = le
    if lt is not None:
        field_kwargs["lt"] = lt

    return field_kwargs


def float_union(
    *,
    ge: float | None = None,
    gt: float | None = None,
    le: float | None = None,
    lt: float | None = None,
) -> float | list[float] | FloatRange:
    field_kwargs = check_annotation_arguments_and_create_kwargs(ge, gt, le, lt)

    return (
        Annotated[float, Field(**field_kwargs)]
        | list[Annotated[float, Field(**field_kwargs)]]
        | Annotated[FloatRange, Field(**field_kwargs)]
    )


def non_negative_float_union(
    *,
    ge: NonNegativeFloat | None = None,
    gt: NonNegativeFloat | None = None,
    le: NonNegativeFloat | None = None,
    lt: NonNegativeFloat | None = None,
) -> NonNegativeFloat | list[NonNegativeFloat] | NonNegativeFloatRange:
    field_kwargs = check_annotation_arguments_and_create_kwargs(ge, gt, le, lt)

    return (
        Annotated[NonNegativeFloat, Field(**field_kwargs)]
        | list[Annotated[NonNegativeFloat, Field(**field_kwargs)]]
        | Annotated[NonNegativeFloatRange, Field(**field_kwargs)]
    )
