VALID_UI_ELEMENTS = [
    "string_input",
    "model_identifier",
    "float_parameter_sweep",
    "int_parameter_sweep",
    "reference",
    "entity_property_dropdown",
]


def validate_hidden_refs_not_required(schema: dict, ref: str) -> None:
    for key, param_schema in schema["properties"].items():
        if param_schema.get("ui_hidden") and key in schema.get("required", []):
            msg = (
                f"The hidden reference {key} is marked as required in the schema"
                f" but shouldn't be\n\n In {ref}"
            )
            raise ValueError(msg)


def validate_string(schema: dict, prop: str, ref: str) -> None:
    value = schema.get(prop)

    if type(value) is not str:
        msg = f"Validation error at {ref}: {prop} must be a string. Got: {type(value)}"
        raise ValueError(msg)


def validate_type(schema: dict, ref: str) -> None:
    if not isinstance(schema, dict):
        msg = f"Validation error at {ref}: 'type' schema must be a dictionary"
        raise TypeError(msg)

    if not schema.get("default"):
        msg = f"Validation error at {ref}: 'type' must have a default"
        raise ValueError(msg)


def validate_block(schema: dict, ref: str) -> None:
    validate_hidden_refs_not_required(schema, ref)

    for key, param_schema in schema.get("properties", {}).items():
        if param_schema.get("ui_hidden"):
            continue

        if key == "type":
            validate_type(param_schema, ref)
            continue

        if param_schema.get("ui_element") not in VALID_UI_ELEMENTS:
            msg = (
                f"Validation error at {ref}: {key} has invalid ui_element:"
                f" {param_schema.get('ui_element')}"
            )

            from pprint import pprint

            pprint(schema)

            raise ValueError(msg)
