import pytest
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import (
    FloatRange,
    IntRange,
    NonNegativeFloatRange,
    NonNegativeIntRange,
    PositiveFloatRange,
    PositiveIntRange,
    check_annotation_arguments_and_create_kwargs,
)


class TestIntRange:
    def test_basic_values(self):
        r = IntRange(start=1, step=1, end=5)
        assert r.values == [1, 2, 3, 4, 5]

    def test_with_step(self):
        r = IntRange(start=0, step=2, end=10)
        assert r.values == [0, 2, 4, 6, 8, 10]

    def test_step_not_evenly_dividing(self):
        r = IntRange(start=0, step=3, end=10)
        assert r.values == [0, 3, 6, 9]

    def test_single_value_large_step(self):
        r = IntRange(start=0, step=100, end=50)
        assert r.values == [0]

    def test_negative_range(self):
        r = IntRange(start=-5, step=1, end=-1)
        assert r.values == [-5, -4, -3, -2, -1]

    def test_start_ge_end_raises(self):
        with pytest.raises(ValidationError, match="start must be < end"):
            IntRange(start=10, step=1, end=5)

    def test_start_equals_end_raises(self):
        with pytest.raises(ValidationError, match="start must be < end"):
            IntRange(start=5, step=1, end=5)

    def test_step_must_be_positive(self):
        with pytest.raises(ValidationError):
            IntRange(start=0, step=0, end=5)

    def test_step_negative_raises(self):
        with pytest.raises(ValidationError):
            IntRange(start=0, step=-1, end=5)


class TestIntRangeLen:
    def test_len(self):
        r = IntRange(start=0, step=1, end=4)
        assert len(r) == 5

    def test_len_with_step(self):
        r = IntRange(start=0, step=2, end=8)
        assert len(r) == 5


class TestIntRangeIter:
    def test_iter(self):
        r = IntRange(start=1, step=1, end=3)
        assert list(r) == [1, 2, 3]


class TestIntRangeComparisons:
    def test_ge_true(self):
        r = IntRange(start=5, step=1, end=10)
        assert r >= 5

    def test_ge_false(self):
        r = IntRange(start=5, step=1, end=10)
        assert not (r >= 6)

    def test_ge_none(self):
        r = IntRange(start=5, step=1, end=10)
        assert r >= None

    def test_gt_true(self):
        r = IntRange(start=5, step=1, end=10)
        assert r > 4

    def test_gt_false(self):
        r = IntRange(start=5, step=1, end=10)
        assert not (r > 5)

    def test_gt_none(self):
        r = IntRange(start=5, step=1, end=10)
        assert r > None

    def test_le_true(self):
        r = IntRange(start=1, step=1, end=5)
        assert r <= 5

    def test_le_false(self):
        r = IntRange(start=1, step=1, end=5)
        assert not (r <= 4)

    def test_le_none(self):
        r = IntRange(start=1, step=1, end=5)
        assert r <= None

    def test_lt_true(self):
        r = IntRange(start=1, step=1, end=5)
        assert r < 6

    def test_lt_false(self):
        r = IntRange(start=1, step=1, end=5)
        assert not (r < 5)

    def test_lt_none(self):
        r = IntRange(start=1, step=1, end=5)
        assert r < None


class TestFloatRange:
    def test_basic_values(self):
        r = FloatRange(start=0.0, step=0.5, end=2.0)
        assert r.values == [0.0, 0.5, 1.0, 1.5, 2.0]

    def test_decimal_precision(self):
        r = FloatRange(start=0.0, step=0.1, end=0.3)
        assert r.values == [0.0, 0.1, 0.2, 0.3]
        # All values should be clean floats with 1 decimal
        for v in r.values:
            assert len(str(v).split(".")[-1]) <= 1

    def test_step_larger_than_range(self):
        r = FloatRange(start=0.0, step=10.0, end=5.0)
        assert r.values == [0.0]

    def test_start_ge_end_raises(self):
        with pytest.raises(ValidationError, match="start must be < end"):
            FloatRange(start=5.0, step=0.1, end=2.0)

    def test_step_must_be_positive(self):
        with pytest.raises(ValidationError):
            FloatRange(start=0.0, step=0.0, end=1.0)


class TestFloatRangeComparisons:
    def test_ge_true(self):
        r = FloatRange(start=1.0, step=0.5, end=3.0)
        assert r >= 1.0

    def test_ge_false(self):
        r = FloatRange(start=1.0, step=0.5, end=3.0)
        assert not (r >= 1.5)

    def test_ge_none(self):
        r = FloatRange(start=1.0, step=0.5, end=3.0)
        assert r >= None

    def test_gt_true(self):
        r = FloatRange(start=1.0, step=0.5, end=3.0)
        assert r > 0.9

    def test_le_true(self):
        r = FloatRange(start=1.0, step=0.5, end=3.0)
        assert r <= 3.0

    def test_lt_true(self):
        r = FloatRange(start=1.0, step=0.5, end=3.0)
        assert r < 3.1


class TestFloatRangeIterAndLen:
    def test_iter(self):
        r = FloatRange(start=0.0, step=1.0, end=2.0)
        assert list(r) == [0.0, 1.0, 2.0]

    def test_len(self):
        r = FloatRange(start=0.0, step=1.0, end=2.0)
        assert len(r) == 3


class TestPositiveIntRange:
    def test_valid(self):
        r = PositiveIntRange(start=1, step=1, end=5)
        assert r.values == [1, 2, 3, 4, 5]

    def test_zero_start_raises(self):
        with pytest.raises(ValidationError):
            PositiveIntRange(start=0, step=1, end=5)

    def test_negative_start_raises(self):
        with pytest.raises(ValidationError):
            PositiveIntRange(start=-1, step=1, end=5)


class TestNonNegativeIntRange:
    def test_valid_with_zero(self):
        r = NonNegativeIntRange(start=0, step=1, end=3)
        assert r.values == [0, 1, 2, 3]

    def test_negative_start_raises(self):
        with pytest.raises(ValidationError):
            NonNegativeIntRange(start=-1, step=1, end=3)


class TestPositiveFloatRange:
    def test_valid(self):
        r = PositiveFloatRange(start=0.1, step=0.1, end=0.3)
        assert len(r.values) == 3

    def test_zero_start_raises(self):
        with pytest.raises(ValidationError):
            PositiveFloatRange(start=0.0, step=0.1, end=1.0)


class TestNonNegativeFloatRange:
    def test_valid_with_zero(self):
        r = NonNegativeFloatRange(start=0.0, step=0.5, end=1.0)
        assert r.values == [0.0, 0.5, 1.0]

    def test_negative_start_raises(self):
        with pytest.raises(ValidationError):
            NonNegativeFloatRange(start=-0.1, step=0.1, end=1.0)


class TestMaxNCoordinates:
    def test_exceeds_max_raises(self):
        r = IntRange(start=0, step=1, end=100)
        with pytest.raises(PydanticCustomError, match="exceeds maximum"):
            _ = r.values


class TestCheckAnnotationArguments:
    def test_ge_only(self):
        result = check_annotation_arguments_and_create_kwargs(ge=0, gt=None, le=None, lt=None)
        assert result == {"ge": 0}

    def test_gt_only(self):
        result = check_annotation_arguments_and_create_kwargs(ge=None, gt=0, le=None, lt=None)
        assert result == {"gt": 0}

    def test_le_only(self):
        result = check_annotation_arguments_and_create_kwargs(ge=None, gt=None, le=10, lt=None)
        assert result == {"le": 10}

    def test_lt_only(self):
        result = check_annotation_arguments_and_create_kwargs(ge=None, gt=None, le=None, lt=10)
        assert result == {"lt": 10}

    def test_ge_and_le(self):
        result = check_annotation_arguments_and_create_kwargs(ge=0, gt=None, le=10, lt=None)
        assert result == {"ge": 0, "le": 10}

    def test_ge_and_gt_raises(self):
        with pytest.raises(OBIONEError, match="Only one of ge or gt can be provided"):
            check_annotation_arguments_and_create_kwargs(ge=0, gt=0, le=None, lt=None)

    def test_le_and_lt_raises(self):
        with pytest.raises(OBIONEError, match="Only one of le or lt can be provided"):
            check_annotation_arguments_and_create_kwargs(ge=None, gt=None, le=10, lt=10)

    def test_all_none(self):
        result = check_annotation_arguments_and_create_kwargs(ge=None, gt=None, le=None, lt=None)
        assert result == {}


class TestIntRangeValuesCaching:
    def test_values_computed_once(self):
        r = IntRange(start=0, step=1, end=5)
        v1 = r.values
        v2 = r.values
        assert v1 is v2
