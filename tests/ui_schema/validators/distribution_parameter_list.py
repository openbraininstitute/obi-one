"""Validator for the `distribution_parameter_list` block UI element."""

from obi_one.core.schema import SchemaKey, UIElement

from .shared import openapi_schema, resolve_ref


def validate_distribution_parameter_list(schema: dict, param: str, ref: str) -> None:
    """A list of `{name, value}` rows whose names come from the sibling `function`.

    The function is the source of truth: the component reads the `{placeholders}` of the
    sibling `function` field in the same block and shows one row per extra placeholder. So the
    block must have a `function` rendered as a `distance_function_input`. Each row edits a
    string `name` and an `OptimizationValue` (`mode` fixed/bounds, `value`, `bounds`).
    """
    where = f"Validation error at {ref}: distribution_parameter_list param {param}"
    assert schema.get("type") == "array", f"{where} should be of type 'array'"
    assert schema.get("default") == [], f"{where} should default to an empty list"

    block = resolve_ref(openapi_schema, ref)
    function = block.get("properties", {}).get("function")
    assert function is not None, f"{where} needs a sibling 'function' field in the same block"
    assert function.get(SchemaKey.UI_ELEMENT) == UIElement.DISTANCE_FUNCTION_INPUT, (
        f"{where}: sibling 'function' should use ui_element '{UIElement.DISTANCE_FUNCTION_INPUT}'"
    )

    item_ref = schema.get("items", {}).get("$ref")
    assert item_ref, f"{where} items should be a $ref to the row block"
    item = resolve_ref(openapi_schema, item_ref)
    properties = item.get("properties", {})
    assert set(item.get("required", [])) >= {"name", "value"}, (
        f"{where} rows should require 'name' and 'value'"
    )
    name = properties.get("name", {})
    assert name.get("type") == "string", f"{where} row 'name' should be a string"
    assert name.get("pattern"), f"{where} row 'name' should carry an identifier pattern"

    value_ref = properties.get("value", {}).get("$ref")
    assert value_ref, f"{where} row 'value' should be a $ref to OptimizationValue"
    value = resolve_ref(openapi_schema, value_ref)
    assert {"mode", "value", "bounds"} <= set(value.get("properties", {})), (
        f"{where} row 'value' should expose 'mode', 'value' and 'bounds'"
    )
    assert value["properties"]["mode"].get("enum") == ["fixed", "bounds"], (
        f"{where} row 'value.mode' should be one of ['fixed', 'bounds']"
    )
