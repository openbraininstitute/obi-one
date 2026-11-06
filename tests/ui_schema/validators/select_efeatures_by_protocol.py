"""Validator for the `select_efeatures_by_protocol` block UI element."""

from .shared import openapi_schema, resolve_ref


def validate_select_efeatures_by_protocol(schema: dict, param: str, ref: str) -> None:
    location = f"{param} at {ref}"

    # The field is a `$ref` to the object backing the widget (with the extras as
    # siblings), so the `object` type the component spec requires lives on the
    # referenced schema rather than on the field itself.
    target_ref = schema.get("$ref") or (schema.get("allOf") or [{}])[0].get("$ref")
    assert target_ref is not None, (
        f"Validation error at {location}: select_efeatures_by_protocol param {param}"
        " should reference the object holding the selection"
    )
    assert resolve_ref(openapi_schema, target_ref).get("type") == "object", (
        f"Validation error at {location}: select_efeatures_by_protocol param {param}"
        " should reference a schema of type 'object'"
    )
    # Which efeatures are valid per protocol is carried by each protocol's
    # `features` union in the schema, so there is no catalogue extra to check.
