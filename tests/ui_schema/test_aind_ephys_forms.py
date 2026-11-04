"""The AIND ephys forms expose every science parameter, in enhanced dropdowns where they choose."""

import pytest

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.kilosort4.config import (
    AINDEPhysSpikeSortingKilosort4ScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.lupin.config import (
    AINDEPhysSpikeSortingLupinScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.spykingcircus2.config import (
    AINDEPhysSpikeSortingSpykingCircus2ScanConfig,
)

from .validators.int_list_optional import validate_int_list_optional
from .validators.int_optional import validate_int_optional
from .validators.json_object import validate_json_object

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


OPTIONAL_INT = {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]}
OPTIONAL_INTS = {"anyOf": [{"type": "array", "items": {"type": "integer"}}, {"type": "null"}]}
FREE_OBJECT = {"type": "object", "additionalProperties": True}


class TestNewElements:
    @pytest.mark.parametrize(
        ("validate", "valid", "invalid"),
        [
            (
                validate_int_optional,
                OPTIONAL_INT,
                {"anyOf": [{"type": "number"}, {"type": "null"}]},
            ),
            (validate_int_optional, OPTIONAL_INT, {"type": "integer"}),
            (validate_int_list_optional, OPTIONAL_INTS, {"type": "array"}),
            (validate_json_object, FREE_OBJECT, {"anyOf": [FREE_OBJECT, {"type": "null"}]}),
            (validate_json_object, FREE_OBJECT, {"type": "string"}),
        ],
    )
    def test_each_accepts_its_shape_only(self, validate, valid, invalid):
        validate(valid, "param", "ref")

        with pytest.raises(Exception, match="param"):
            validate(invalid, "param", "ref")
