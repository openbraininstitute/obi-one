"""Validator for the `object` block UI element."""

from jsonschema import ValidationError

from obi_one.core.schema import SchemaKey, UIElement

from .shared import openapi_schema, resolve_ref, validate_string
from tests.ui_schema.validate_block import validate_block_elements, validate_type

# Nested block-element ui_elements allowed inside an `object`. Restricted to the types used by
# the eFEL / phase-plot / SineSpec settings objects.
OBJECT_PROPERTY_UI_ELEMENTS = frozenset(
    {
        UIElement.BOOLEAN_INPUT,
        UIElement.FLOAT_INPUT,
        UIElement.STRING_INPUT,
        UIElement.STRING_LIST_INPUT,
    }
)


def validate_object(schema: dict, param: str, ref: str) -> None:
    # An `object` is a fixed-shape mapping that becomes a plain dict in Python. Its type is a
    # referenced model, so Pydantic emits it as a `$ref`; resolve it to read the properties.
    if schema.get("$ref"):
        schema = {**resolve_ref(openapi_schema, schema["$ref"]), **schema}
        schema.pop("$ref", None)

    if schema.get("type") != "object":
        msg = f"Validation error at {ref}: object param {param} should be of type 'object'"
        raise ValidationError(msg) from None

    # Additional properties must be forbidden: undeclared keys have no schema to validate against.
    if schema.get("additionalProperties") is not False:
        msg = (
            f"Validation error at {ref}: object param {param} must set "
            "'additionalProperties' to false so every key is schema-validated"
        )
        raise ValidationError(msg) from None

    properties = schema.get("properties", {})
    if not properties:
        msg = (
            f"Validation error at {ref}: object param {param} should declare at least one property"
        )
        raise ValidationError(msg) from None

    for prop, prop_schema in properties.items():
        if prop == "type":
            validate_type(prop_schema, ref)
            continue

        validate_string(prop_schema, "title", f"{prop} at {ref}")
        validate_string(prop_schema, "description", f"{prop} at {ref}")

        prop_ui_element = prop_schema.get(SchemaKey.UI_ELEMENT)
        if prop_ui_element not in OBJECT_PROPERTY_UI_ELEMENTS:
            msg = (
                f"Validation error at {ref}: object param {param} property {prop} has an "
                f"unsupported 'ui_element' {prop_ui_element}. Allowed: "
                f"{sorted(OBJECT_PROPERTY_UI_ELEMENTS)}"
            )
            raise ValidationError(msg) from None

        validate_block_elements(prop, prop_schema, ref)
