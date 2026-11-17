import copy

import pytest

from obi_one.core.schema import SchemaKey, UIElement

from .validators.root.block_info import validate_block_info
from .validators.shared import openapi_schema, resolve_ref

CONFIG = "CircuitSimulationScanConfig"


def _info_schema() -> tuple[dict, str]:
    """Return a deep copy of a real `info` root element, resolved, and its `$ref`."""
    root = openapi_schema["components"]["schemas"][CONFIG]["properties"]["info"]
    ref = root["$ref"]
    return copy.deepcopy({**root, **resolve_ref(openapi_schema, ref)}), ref


def test_every_ui_enabled_config_declares_info_as_block_info():
    for name, schema in openapi_schema["components"]["schemas"].items():
        info = schema.get("properties", {}).get("info")
        if schema.get(SchemaKey.UI_ENABLED) and info is not None:
            assert info[SchemaKey.UI_ELEMENT] == UIElement.BLOCK_INFO, name


def test_real_info_schema_passes_and_keeps_its_properties_required():
    schema, ref = _info_schema()
    validate_block_info(schema, "info", ref, CONFIG, {})
    # The element relaxes the UI, not the schema: generating without them is still refused.
    assert {"campaign_name", "campaign_description"} <= set(schema["required"])


def test_rejects_a_block_without_properties():
    schema, ref = _info_schema()
    del schema["properties"]
    with pytest.raises(TypeError, match="must have 'properties'"):
        validate_block_info(schema, "info", ref, CONFIG, {})


@pytest.mark.parametrize("name", ["campaign_name", "campaign_description"])
def test_rejects_a_block_missing_the_name_or_the_description(name):
    schema, ref = _info_schema()
    del schema["properties"][name]
    with pytest.raises(ValueError, match=f"must have a '{name}' property"):
        validate_block_info(schema, "info", ref, CONFIG, {})


def test_rejects_a_name_that_is_not_a_string_input():
    schema, ref = _info_schema()
    schema["properties"]["campaign_name"][SchemaKey.UI_ELEMENT] = UIElement.FLOAT_INPUT
    with pytest.raises(ValueError, match="with ui_element 'string_input'"):
        validate_block_info(schema, "info", ref, CONFIG, {})
