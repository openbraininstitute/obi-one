"""Validator for the `block_info` root UI element."""

from obi_one.core.schema import SchemaKey, UIElement

from tests.ui_schema.validate_block import validate_block

# The UI shows these when the campaign is generated and writes what is entered into them.
INFO_PROPERTIES = ("campaign_name", "campaign_description")


def validate_block_info(
    schema: dict,
    key: str,
    ref: str,
    config_ref: str,  # ruff: ignore[unused-function-argument]
    form: dict,  # ruff: ignore[unused-function-argument]
) -> None:
    # Uniform root-validator signature (schema, element, ref, config_ref, form); a single block
    # validates in place, so the config_ref/form context is unused here.
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        msg = f"Validation error at {ref}: block_info {key} must have 'properties'"
        raise TypeError(msg)

    for name in INFO_PROPERTIES:
        ui_element = properties.get(name, {}).get(SchemaKey.UI_ELEMENT)
        if ui_element != UIElement.STRING_INPUT:
            msg = (
                f"Validation error at {ref}: block_info {key} must have a '{name}' property"
                f" with ui_element '{UIElement.STRING_INPUT}'. Got: {ui_element}"
            )
            raise ValueError(msg)

    validate_block(schema, ref)
