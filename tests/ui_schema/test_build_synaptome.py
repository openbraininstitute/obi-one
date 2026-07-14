from obi_one.core.info import Info
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.tasks.build_synaptome import (
    BuildSynaptomeScanConfig,
    BuildSynaptomeSingleConfig,
)


def test_memodel_is_supplied_through_initialize_block():
    config = BuildSynaptomeScanConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=BuildSynaptomeScanConfig.Initialize(
            me_model=MEModelFromID(id_str="me-model-id")
        ),
    )

    assert config.initialize.me_model.id_str == "me-model-id"
    assert not hasattr(config, "me_model")

    single_config = config.cast_to_single_coord()
    assert isinstance(single_config, BuildSynaptomeSingleConfig)
    assert single_config.initialize.me_model.id_str == "me-model-id"


def test_schema_uses_initialize_instead_of_memodel_selection():
    schema = BuildSynaptomeScanConfig.model_json_schema()

    assert "initialize" in schema["properties"]
    assert "me_model" not in schema["properties"]
    assert all("MEModelSelection" not in definition for definition in schema["$defs"])
    initialize_schema = schema["$defs"]["Initialize"]
    assert initialize_schema["properties"]["me_model"]["ui_element"] == "model_identifier"
