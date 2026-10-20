"""Validator for the `morphology_location_selection` block UI element."""

import math

from .shared import openapi_schema, resolve_ref


def validate_morphology_location_selection(schema: dict, param: str, ref: str) -> None:
    # The field may be nullable (anyOf: [array-schema, null]), so unwrap to the array branch.
    if "anyOf" in schema:
        array_schemas = [s for s in schema["anyOf"] if s.get("type") == "array"]
        assert len(array_schemas) == 1, (
            f"Validation error at {ref}: morphology_location_selection param {param} should "
            "have exactly one array member in anyOf"
        )
        array_schema = array_schemas[0]
    else:
        array_schema = schema

    assert array_schema.get("type") == "array", (
        f"Validation error at {ref}: morphology_location_selection param {param} should be of "
        "type 'array'"
    )

    resolved_ref = resolve_ref(openapi_schema, array_schema.get("items").get("$ref"))
    properties = resolved_ref.get("properties", {})

    # The widget edits one row per location, so the referenced object must carry exactly the
    # pair the row is made of — anything else and the row would silently drop a field.
    assert set(properties) == {"section_id", "offset"}, (
        f"Validation error at {ref}: morphology_location_selection param {param} should "
        f"reference a schema with exactly 'section_id' and 'offset'. Got: {sorted(properties)}"
    )

    location = f"{param} at {ref}"

    section_id = properties["section_id"]
    assert section_id.get("type") == "integer", (
        f"Validation error at {location}: morphology_location_selection 'section_id' should be "
        "of type 'integer'"
    )
    assert section_id.get("minimum") == 0, (
        f"Validation error at {location}: morphology_location_selection 'section_id' should "
        "have minimum 0 (SONATA reserves 0 for the soma)"
    )

    offset = properties["offset"]
    assert offset.get("type") == "number", (
        f"Validation error at {location}: morphology_location_selection 'offset' should be of "
        "type 'number'"
    )
    assert math.isclose(offset.get("minimum"), 0.0), (
        f"Validation error at {location}: morphology_location_selection 'offset' should have "
        "minimum 0.0"
    )
    assert math.isclose(offset.get("maximum"), 1.0), (
        f"Validation error at {location}: morphology_location_selection 'offset' should have "
        "maximum 1.0"
    )
