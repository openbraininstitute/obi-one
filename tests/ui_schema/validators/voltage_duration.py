"""Validator for the `voltage_duration` block UI element."""

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units

from .shared import openapi_schema, resolve_ref


def validate_voltage_duration(schema: dict, param: str, ref: str) -> None:
    assert schema.get("type") == "array", (
        f"Validation error at {ref}: voltage_duration param {param} should be of type 'array'"
    )
    assert schema.get("ui_element") == UIElement.VOLTAGE_DURATION, (
        f"Validation error at {ref}: voltage_duration param {param} should have ui_element "
        f"'{UIElement.VOLTAGE_DURATION}'"
    )

    resolved_ref = resolve_ref(openapi_schema, schema.get("items").get("$ref"))
    assert (
        resolved_ref.get("properties").get("type").get("const") == "DurationVoltageCombination"
    ), (
        f"Validation error at {ref}: voltage_duration param {param} should reference a schema "
        "with type 'DurationVoltageCombination'"
    )
    voltage = resolved_ref.get("properties").get("voltage")
    assert voltage["anyOf"] == [
        {"type": "number"},
        {"type": "array", "items": {"type": "number"}},
    ], (
        f"Validation error at {ref}: voltage_duration param {param} should reference a schema "
        f"where 'voltage' is of type 'number' or an array of 'number'."
    )
    assert voltage.get(SchemaKey.UNITS) == Units.MILLIVOLTS, (
        f"Validation error at {ref}: voltage_duration param {param} should reference a schema "
        "where 'voltage' has units 'millivolts'"
    )

    duration = resolved_ref.get("properties").get("duration")
    assert duration["anyOf"] == [
        {"type": "number", "minimum": 0.0},
        {"type": "array", "items": {"type": "number", "minimum": 0.0}},
    ], (
        f"Validation error at {ref}: voltage_duration param {param} should reference a schema "
        f"where 'duration' is of type 'number' or an array of 'number'. Found {duration}"
    )
    assert duration.get(SchemaKey.UNITS) == Units.MILLISECONDS, (
        f"Validation error at {ref}: voltage_duration param {param} should reference a schema "
        "where 'duration' has units 'milliseconds'"
    )
