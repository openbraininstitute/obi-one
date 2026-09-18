"""Shared helpers and OpenAPI schema for block UI-element validators.

This module holds the pieces that more than one validator relies on: the generated
OpenAPI schema, `$ref` resolution, and the small primitive validators (string, enum,
list-of-strings, numeric union) plus the enhanced-string helpers. Keep the per-element
validators in their own modules and import the shared pieces from here.
"""

import math
import sys
from enum import StrEnum

from fastapi.openapi.utils import get_openapi
from jsonschema import RefResolver, ValidationError, validate

from app.application import app
from obi_one.core.schema import SchemaKey

openapi_schema = get_openapi(
    title=app.title,
    version=app.version,
    openapi_version=app.openapi_version,
    description=app.description,
    routes=app.routes,
)


def resolve_ref(openapi_schema: dict, ref: str) -> dict:
    resolver = RefResolver.from_schema(openapi_schema)
    _, resolved_node = resolver.resolve(ref)
    return resolved_node


def validate_string(schema: dict, prop: str, ref: str) -> None:
    value = schema.get(prop)

    if type(value) is not str:
        msg = f"Validation error at {ref}: {prop} must be a string. Got: {type(value)}"
        raise ValueError(msg)


def validate_enum_value(schema: dict, prop: str, enum_type: type[StrEnum], ref: str) -> None:
    value = schema.get(prop)
    allowed_values = {member.value for member in enum_type}
    if value not in allowed_values:
        msg = (
            f"Validation error at {ref}: {prop} must be one of {sorted(allowed_values)}. "
            f"Got: {value}"
        )
        raise ValueError(msg)


def validate_list_strings(schema: dict, prop: str, ref: str) -> None:
    value = schema.get(prop, [])
    if type(value) is not list or not all(isinstance(item, str) for item in value):
        msg = f"Validation error at {ref}: {prop} must be a list of strings. Got: {value}"
        raise ValueError(msg)


def validate_string_param(schema: dict, param: str, ref: str) -> None:
    try:
        validate("a", schema)

    except ValidationError:
        msg = f"Validation error at {ref}: string_input param {param} failedto validate a string"
        raise ValidationError(msg) from None


def determine_minimum_valid_numeric_value(schema: dict) -> float | int:
    default = schema.get("default")
    single_type = schema.get("anyOf", [{}])[0]

    if single_type.get("type") == "integer":
        minimum = single_type.get("minimum", None)
        if minimum is None:
            minimum = single_type.get("exclusiveMinimum", -sys.maxsize)
            minimum += 1

        maximum = single_type.get("maximum", None)
        if maximum is None:
            maximum = single_type.get("exclusiveMaximum", sys.maxsize)
            maximum -= 1

    elif single_type.get("type") == "number":
        minimum = single_type.get("minimum", None)
        if minimum is None:
            minimum = single_type.get("exclusiveMinimum", -sys.float_info.max)
            minimum += math.ulp(minimum)

        maximum = single_type.get("maximum", None)
        if maximum is None:
            maximum = single_type.get("exclusiveMaximum", sys.float_info.max)
            maximum -= math.ulp(maximum)

    # Logical check if minimum less than or equal to maximum
    if not minimum <= maximum:
        msg = "minimum is not less than or equal maximum, invalid schema"
        raise ValidationError(msg)

    # Logical checks for default consistency
    if default is not None and not minimum <= default <= maximum:
        msg = "default is less than minimum or greater than maximum, invalid schema"
        raise ValidationError(msg)

    return minimum


def validate_numeric_single_and_list_types(
    schema: dict, param: str, ref: str, data_type: str, ui_element: str
) -> None:
    if schema.get("anyOf", [{}])[0].get("type") != data_type:
        msg = (
            f"Validation error at {ref}: {ui_element} param {param} should "
            f"be a union with a '{data_type}' as first element"
        )
        raise ValidationError(msg) from None

    if schema.get("anyOf", [{}])[1].get("type") != "array":
        msg = (
            f"Validation error at {ref}: {ui_element} param {param} should "
            "be a union with an 'array' as second element"
        )
        raise ValidationError(msg) from None

    if schema.get("anyOf", [{}])[0] != schema.get("anyOf", [{}])[1].get("items"):
        msg = (
            f"Validation error at {ref}: {ui_element} param {param} should "
            "have matching types for single value and array items"
        )
        raise ValidationError(msg) from None


def resolve_union_reference_types(union_members: list) -> list:
    """Return the default `type` values of the BlockReference members of a union.

    Each reference union member is a `$ref` to a BlockReference schema whose `type` property
    defaults to its class name. Non-`$ref` members (e.g. the `null` of a nullable union) are
    skipped.
    """
    reference_types = []
    for union_member in union_members:
        if (member_ref := union_member.get("$ref")) is None:
            continue
        member_schema = resolve_ref(openapi_schema, member_ref)
        reference_types.append(member_schema.get("properties", {}).get("type", {}).get("default"))
    return reference_types


def validate_dictionary_by_enum_key(
    param: str, ref: str, enum_list: list, dictionary_by_enum_key: dict, dictionary_name: str
) -> None:
    if dictionary_by_enum_key is None:
        return

    # Check that description_by_key is a dict
    if type(dictionary_by_enum_key) is not dict:
        msg = (
            f"Validation error at {ref}: enhanced string param {param} should "
            f"'{dictionary_name}' be a dictionary"
        )
        raise ValidationError(msg) from None

    # Check that description_by_key has a key for each enum key
    if sorted(enum_list) != sorted(dictionary_by_enum_key.keys()):
        msg = (
            f"Validation error at {ref}: enhanced string param {param} has "
            f"'{dictionary_name}' with keys different from 'enum' values"
        )
        raise ValidationError(msg) from None

    # Check that each description is a string
    if not all(isinstance(val, str) for val in dictionary_by_enum_key.values()):
        msg = (
            f"Validation error at {ref}: enhanced string param {param} has "
            f"a non-string description in '{dictionary_name}'"
        )
        raise ValidationError(msg) from None


def validate_enhanced_string_fields(schema: dict, param: str, ref: str, enum_list: list) -> None:
    description_by_key = schema.get(SchemaKey.DESCRIPTION_BY_KEY)
    latex_by_key = schema.get(SchemaKey.LATEX_BY_KEY)
    title_by_key = schema.get(SchemaKey.TITLE_BY_KEY)

    # Make sure at least one of description_by_key or latex_by_key exists
    if description_by_key is None and latex_by_key is None:
        msg = (
            f"Validation error at {ref}: enhanced string param {param} should "
            "have at least one of 'description_by_key' and 'latex_by_key' fields in its schema"
        )
        raise ValidationError(msg) from None

    if title_by_key is None:
        msg = (
            f"Validation error at {ref}: enhanced string param {param} should "
            "have a 'title_by_key' field in its schema"
        )
        raise ValidationError(msg) from None

    # Validate title_by_key, description_by_key, latex_by_key dictionaries
    validate_dictionary_by_enum_key(
        param, ref, enum_list, description_by_key, SchemaKey.DESCRIPTION_BY_KEY
    )
    validate_dictionary_by_enum_key(param, ref, enum_list, latex_by_key, SchemaKey.LATEX_BY_KEY)
    validate_dictionary_by_enum_key(param, ref, enum_list, title_by_key, SchemaKey.TITLE_BY_KEY)
