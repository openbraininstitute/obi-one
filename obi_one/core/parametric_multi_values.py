import math
from decimal import Decimal
from typing import Annotated, Self

import numpy as np
from pydantic import (
    Discriminator,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)
from pydantic_core import PydanticCustomError

from obi_one.core.base import OBIBaseModel
from obi_one.core.exception import OBIONEError

MAX_N_COORDINATES = 100


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

    @classmethod
    def check_n_less_equal_max(cls, n: int, max_n: int) -> None:
        """Check if the number of values is less than or equal to n."""
        if n > max_n:
            exception_name = "custom_n_greater_than_max"
            raise PydanticCustomError(
                exception_name,
                f"Number of values {n} exceeds maximum allowed {max_n}.",
            )

    def check_expected_values_length(self, expected_length: int) -> None:
        """Check if the number of expected values is equal to the actual number of values."""
        if len(self._values) != expected_length:
            exception_name = "custom_expected_length_mismatch"
            raise PydanticCustomError(
                exception_name,
                f"Expected {expected_length} values, but got {len(self._values)} values.",
            )


class IntRange(ParametericMultiValue):
    start: int
    step: PositiveInt
    end: int
    _values: list[int] | None = None

    # @model_validator(mode="after")
    @property
    def values(self) -> list[int]:
        if self._values is None:
            self._values = list(range(self.start, self.end + 1, self.step))

            range_over_step = (Decimal(str(self.end)) - Decimal(str(self.start))) / Decimal(
                str(self.step)
            )
            floor_range_over_step = math.floor(range_over_step)
            n = floor_range_over_step + 1

            ParametericMultiValue.check_n_less_equal_max(n, MAX_N_COORDINATES)

            self._values = list(
                range(self.start, self.end + 1, self.step)
            )  # + 1 includes end in range

            self.check_expected_values_length(n)

        return self._values

    def __ge__(self, v: int | None) -> bool:
        """Greater than or equal to operator."""
        if v is None:
            return True
        return all(_v >= v for _v in self.values)

    def __gt__(self, v: int | None) -> bool:
        """Greater than operator."""
        if v is None:
            return True
        return all(_v > v for _v in self.values)

    def __le__(self, v: int | None) -> bool:
        """Less than or equal to operator."""
        if v is None:
            return True
        return all(_v <= v for _v in self.values)

    def __lt__(self, v: int | None) -> bool:
        """Less than operator."""
        if v is None:
            return True
        return all(_v < v for _v in self.values)

    def __iter__(self) -> int:
        """Iterator."""
        return self.values.__iter__()


class FloatRange(ParametericMultiValue):
    start: float
    step: PositiveFloat
    end: float
    _values: list[float] | None = None

    @property
    def values(self) -> list[float]:
        if self._values is None:
            range_over_step = (Decimal(str(self.end)) - Decimal(str(self.start))) / Decimal(
                str(self.step)
            )
            floor_range_over_step = math.floor(range_over_step)
            n = floor_range_over_step + 1
            ParametericMultiValue.check_n_less_equal_max(n, MAX_N_COORDINATES)

            self._values = np.linspace(
                self.start, self.start + floor_range_over_step * self.step, n
            )

            self.check_expected_values_length(n)

            decimals = len(str(self.step).split(".")[-1])

            q = Decimal(1).scaleb(
                -decimals
            )  # Shift decimal point of 1 to the left by 'decimals' places
            self._values = [float(Decimal(str(v)).quantize(q)) for v in self._values]

        return self._values

    def __ge__(self, v: float | None) -> bool:
        """Greater than or equal to operator."""
        if v is None:
            return True
        return all(_v >= v for _v in self.values)

    def __gt__(self, v: float | None) -> bool:
        """Greater than operator."""
        if v is None:
            return True
        return all(_v > v for _v in self.values)

    def __le__(self, v: float | None) -> bool:
        """Less than or equal to operator."""
        if v is None:
            return True
        return all(_v <= v for _v in self.values)

    def __lt__(self, v: float | None) -> bool:
        """Less than operator."""
        if v is None:
            return True
        return all(_v < v for _v in self.values)

    def __iter__(self) -> float:
        """Iterator."""
        return self.values.__iter__()


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


ParametericMultiValueUnion = Annotated[
    (
        IntRange
        | PositiveIntRange
        | NonNegativeIntRange
        | FloatRange
        | PositiveFloatRange
        | NonNegativeFloatRange
    ),
    Discriminator("type"),
]
