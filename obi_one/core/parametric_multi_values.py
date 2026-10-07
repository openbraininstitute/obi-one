"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import]

from obi_one_lazy.core.parametric_multi_values import (
    Annotated,
    check_annotation_arguments_and_create_kwargs,
    Decimal,
    Discriminator,
    Field,
    float_union,
    FloatRange,
    IntRange,
    math,
    MAX_N_COORDINATES,
    model_validator,
    non_negative_float_union,
    NonNegativeFloat,
    NonNegativeFloatRange,
    NonNegativeFloatUnion,
    NonNegativeInt,
    NonNegativeIntRange,
    np,
    OBIBaseModel,
    OBIONEError,
    ParametericMultiValue,
    ParametericMultiValueUnion,
    PositiveFloat,
    PositiveFloatRange,
    PositiveInt,
    PositiveIntRange,
    PydanticCustomError,
    Self,
)
