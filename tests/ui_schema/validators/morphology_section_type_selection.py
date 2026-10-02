"""Validator for the `morphology_section_type_selection` block UI element."""

from jsonschema import ValidationError, validate

from obi_one.core.schema import SchemaKey
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
    MorphologyMappedProperties,
)

from .shared import validate_enum_value


def validate_morphology_section_type_selection(schema: dict, param: str, ref: str) -> None:
    validate_enum_value(
        schema,
        SchemaKey.PROPERTY_GROUP,
        MappedPropertiesGroup,
        f"{param} at {ref}",
    )
    validate_enum_value(
        schema,
        SchemaKey.PROPERTY,
        MorphologyMappedProperties,
        f"{param} at {ref}",
    )

    any_of = schema.get("anyOf", [])
    if len(any_of) != 3:
        msg = (
            f"Validation error at {ref}: morphology_section_type_selection param {param} "
            "should be a union of array[int], array[array[int]], and null"
        )
        raise ValidationError(msg)

    single_selection_schema, scan_schema, null_schema = any_of
    if (
        single_selection_schema.get("type") != "array"
        or single_selection_schema.get("items", {}).get("type") != "integer"
    ):
        msg = (
            f"Validation error at {ref}: morphology_section_type_selection param {param} "
            "should have array[int] as its first union member"
        )
        raise ValidationError(msg)

    scan_items = scan_schema.get("items", {})
    if (
        scan_schema.get("type") != "array"
        or scan_items.get("type") != "array"
        or scan_items.get("items", {}).get("type") != "integer"
    ):
        msg = (
            f"Validation error at {ref}: morphology_section_type_selection param {param} "
            "should have array[array[int]] as its second union member"
        )
        raise ValidationError(msg)

    if null_schema.get("type") != "null":
        msg = (
            f"Validation error at {ref}: morphology_section_type_selection param {param} "
            "should have null as its third union member"
        )
        raise ValidationError(msg)

    try:
        validate([3, 4], schema)
        validate([[3], [3, 4]], schema)
        validate(None, schema)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: morphology_section_type_selection param {param} "
            "failed to validate supported values"
        )
        raise ValidationError(msg) from None
