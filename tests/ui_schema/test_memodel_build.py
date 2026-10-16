from obi_one.scientific.tasks.memodel_build import MEModelBuildScanConfig


def test_inputs_are_single_entity_selectors():
    schema = MEModelBuildScanConfig.model_json_schema()
    initialize = schema["$defs"]["Initialize"]["properties"]

    assert initialize["morphology"]["ui_element"] == "model_selector_single"
    assert initialize["morphology"]["entity_query"] == {"type": "cell_morphology"}
    assert initialize["emodel"]["ui_element"] == "model_selector_single"
    assert initialize["emodel"]["entity_query"] == {"type": "emodel"}


def test_groups():
    schema = MEModelBuildScanConfig.model_json_schema()

    assert schema["ui_enabled"] is True
    assert schema["group_order"] == ["Setup", "Inputs"]
    assert schema["properties"]["initialize"]["group"] == "Inputs"
