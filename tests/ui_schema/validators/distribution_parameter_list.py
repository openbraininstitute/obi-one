"""Validator for the `distribution_parameter_list` block UI element."""

from obi_one.core.schema import SchemaKey

from .shared import openapi_schema, resolve_ref


def validate_distribution_parameter_list(schema: dict, param: str, ref: str) -> None:
    """A list of `{name, value}` rows whose names come from a sibling function's placeholders.

    The component reads the sibling named by `parameters_from`, extracts its `{placeholders}`
    and prompts for one row per extra placeholder. Each row edits a string `name` and an
    `OptimizationValue` (`mode` fixed/bounds, `value`, `bounds`).
    """
    where = f"Validation error at {ref}: distribution_parameter_list param {param}"
    assert schema.get("type") == "array", f"{where} should be of type 'array'"
    assert schema.get("default") == [], f"{where} should default to an empty list"

    source = schema.get(SchemaKey.PARAMETERS_FROM)
    assert isinstance(source, str), f"{where} should name its source field in 'parameters_from'"
    block = resolve_ref(openapi_schema, ref)
    sibling = block.get("properties", {}).get(source)
    assert sibling is not None, f"{where}: 'parameters_from' field '{source}' is not a sibling"
    assert sibling.get("type") == "string", f"{where}: '{source}' should be a string field"

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
