"""The AIND ephys forms expose every science parameter, in enhanced dropdowns where they choose."""

import pytest

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.aind_ephys._01_preprocessing.config import (
    AINDEPhysPreprocessingScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.kilosort4.config import (
    AINDEPhysSpikeSortingKilosort4ScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.lupin.config import (
    AINDEPhysSpikeSortingLupinScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.spykingcircus2.config import (
    AINDEPhysSpikeSortingSpykingCircus2ScanConfig,
)

from .validators.entity_property_multi_select import validate_entity_property_multi_select

FORMS = [
    AINDEPhysPreprocessingScanConfig,
    AINDEPhysSpikeSortingKilosort4ScanConfig,
    AINDEPhysSpikeSortingSpykingCircus2ScanConfig,
    AINDEPhysSpikeSortingLupinScanConfig,
]
# Execution settings the platform defines, and local paths a launch job could not see.
NOT_IN_THE_FORM = {
    "dispatch",
    "job_kwargs",
    "runtime",
    "cache_preprocessing_mode",
    "nwb_path",
    "preprocessing_output_path",
}


def form_fields(form) -> list[tuple[str, dict]]:
    schema = form.model_json_schema()
    definitions = schema["$defs"]

    def resolve(field: dict) -> dict:
        return {**definitions[field["$ref"].split("/")[-1]], **field} if "$ref" in field else field

    fields = []
    for name, root in schema["properties"].items():
        if name in NOT_IN_THE_FORM or name == "type":
            continue
        fields.append((name, root))
        variants = root.get("oneOf", [root])
        for block in map(resolve, variants):
            fields += [
                (field_name, field)
                for field_name, field in block["properties"].items()
                if field_name not in NOT_IN_THE_FORM and field_name != "type"
            ]
    return fields


class TestForms:
    @pytest.mark.parametrize("form", FORMS)
    def test_every_field_is_in_the_form(self, form):
        hidden = [name for name, field in form_fields(form) if SchemaKey.UI_ELEMENT not in field]

        assert not hidden

    @pytest.mark.parametrize("form", FORMS)
    def test_every_dropdown_describes_its_options(self, form):
        plain = [
            name
            for name, field in form_fields(form)
            if field.get(SchemaKey.UI_ELEMENT) == UIElement.STRING_SELECTION
        ]

        assert not plain

    def test_the_filter_and_the_denoising_are_each_a_choice(self):
        properties = AINDEPhysPreprocessingScanConfig.model_json_schema()["properties"]

        for name in ("temporal_filter", "denoising"):
            assert properties[name][SchemaKey.UI_ELEMENT] == UIElement.BLOCK_UNION
            assert properties[name]["default"]["type"]

    def test_the_template_matching_is_a_choice(self):
        properties = AINDEPhysSpikeSortingSpykingCircus2ScanConfig.model_json_schema()["properties"]

        assert properties["matching"][SchemaKey.UI_ELEMENT] == UIElement.BLOCK_UNION
        assert properties["matching"]["default"]["type"]

    def test_the_channels_to_ignore_are_chosen_from_the_recording(self):
        schema = AINDEPhysPreprocessingScanConfig.model_json_schema()
        field = schema["$defs"]["Initialize"]["properties"]["channels_to_ignore"]
        group = field[SchemaKey.PROPERTY_GROUP]

        validate_entity_property_multi_select(field, "channels_to_ignore", "Initialize")
        assert field["default"] == []
        assert "{recording_id}" in schema[SchemaKey.PROPERTY_ENDPOINTS][group]


CHOICE = {SchemaKey.PROPERTY_GROUP: "Group", SchemaKey.PROPERTY: "Items"}
STRINGS = {"type": "array", "items": {"type": "string"}}


class TestMultiSelectValidator:
    def test_it_accepts_a_list_of_strings_with_its_property(self):
        validate_entity_property_multi_select({**STRINGS, **CHOICE}, "param", "ref")

    @pytest.mark.parametrize(
        "invalid",
        [
            STRINGS,
            {"type": "array", "items": {"type": "integer"}, **CHOICE},
            {"anyOf": [STRINGS, {"type": "null"}], **CHOICE},
            {"type": "string", **CHOICE},
            {**STRINGS, "minItems": 1, **CHOICE},
        ],
    )
    def test_it_refuses_anything_else(self, invalid):
        with pytest.raises(Exception, match="param"):
            validate_entity_property_multi_select(invalid, "param", "ref")
