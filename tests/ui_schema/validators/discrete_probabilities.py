"""Validator for the `discrete_probabilities` block UI element."""

from obi_one.core.schema import SchemaKey

from .shared import openapi_schema, resolve_ref


def validate_discrete_probabilities(schema: dict, param: str, ref: str) -> None:
    """The element edits two fields, so both halves of that pair are checked here.

    The component reads the sibling `probabilities` off the block's state by name. Nothing in
    the component can notice if that field is renamed, retyped, or made visible - it would
    simply render an empty column, or a second list editor beside the table that can put the
    two arrays at different lengths. This is where that contract is held.
    """
    assert schema.get("type") == "array", (
        f"Validation error at {ref}: discrete_probabilities param {param} should be of type 'array'"
    )
    assert schema.get("items") == {"type": "integer"}, (
        f"Validation error at {ref}: discrete_probabilities param {param} should be an array of "
        "integers"
    )

    block = resolve_ref(openapi_schema, ref)
    probabilities = block.get("properties", {}).get("probabilities")
    assert probabilities is not None, (
        f"Validation error at {ref}: discrete_probabilities param {param} needs a sibling "
        "'probabilities' field, which the same element edits"
    )
    assert probabilities.get("type") == "array", (
        f"Validation error at {ref}: 'probabilities' should be of type 'array'"
    )
    assert probabilities.get("items") == {"type": "number"}, (
        f"Validation error at {ref}: 'probabilities' should be an array of numbers"
    )
    assert probabilities.get(SchemaKey.UI_HIDDEN) is True, (
        f"Validation error at {ref}: 'probabilities' should be {SchemaKey.UI_HIDDEN}, because "
        f"the discrete_probabilities element on {param} edits it as part of the same table. "
        "Shown separately, the two arrays could be given different lengths."
    )
