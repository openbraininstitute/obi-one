"""Validator for the `ion_channel_model_properties` block UI element."""

from jsonschema import RefResolver, ValidationError, validate

from .shared import accepts_null, openapi_schema, resolve_ref, validate_string

ID = "00000000-0000-0000-0000-000000000000"

# Every property is nullable: null means "take it from the recordings".
PROPERTIES = {
    "ion_channel_name": "Kv6_2",
    "temperature": 34.5,
    "species": {"type": "SpeciesFromID", "id_str": ID},
    "strain": {"type": "StrainFromID", "id_str": ID},
    "brain_region": {"type": "BrainRegionFromID", "id_str": ID},
}


def _accepts(schema: dict, value: object) -> bool:
    try:
        validate(value, schema, resolver=RefResolver.from_schema(openapi_schema))
    except ValidationError:
        return False
    return True


def validate_ion_channel_model_properties(schema: dict, param: str, ref: str) -> None:
    if not isinstance(schema.get("default"), dict):
        msg = f"Validation error at {ref}: {param} should have an object default"
        raise ValidationError(msg) from None

    if schema.get("$ref"):
        schema = {**resolve_ref(openapi_schema, schema["$ref"]), **schema}
        schema.pop("$ref", None)

    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        msg = (
            f"Validation error at {ref}: {param} should be an object with "
            "'additionalProperties' false"
        )
        raise ValidationError(msg) from None

    properties = schema.get("properties", {})
    if set(properties) != {"type", *PROPERTIES}:
        msg = (
            f"Validation error at {ref}: {param} should have exactly the properties "
            f"{sorted(PROPERTIES)}, got {sorted(set(properties) - {'type'})}"
        )
        raise ValidationError(msg) from None

    for prop, value in PROPERTIES.items():
        prop_schema = properties[prop]
        validate_string(prop_schema, "title", f"{prop} at {ref}")
        validate_string(prop_schema, "description", f"{prop} at {ref}")
        if not accepts_null(prop_schema) or prop_schema.get("default") is not None:
            msg = f"Validation error at {ref}: {param}.{prop} should be nullable, default null"
            raise ValidationError(msg) from None
        if not _accepts(prop_schema, value):
            msg = f"Validation error at {ref}: {param}.{prop} should accept {value!r}"
            raise ValidationError(msg) from None

    if _accepts(properties["ion_channel_name"], "6.2"):
        msg = f"Validation error at {ref}: {param}.ion_channel_name should be a NEURON identifier"
        raise ValidationError(msg) from None
