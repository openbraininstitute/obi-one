import json

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS,
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
    tsodyks_markram_default_distributions,
)
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationScanConfig,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag


def _reference_fields(model_class):
    """The model's reference fields, by name, with their json_schema_extra."""
    return {
        name: field.json_schema_extra
        for name, field in model_class.model_fields.items()
        if isinstance(field.json_schema_extra, dict)
        and SchemaKey.REFERENCE_TYPES in field.json_schema_extra
    }


def _config_tag_defaults():
    return SynapseParameterizationScanConfig.json_schema_extra_additions[
        SchemaKey.REFERENCE_TAG_DEFAULTS
    ]


def test_every_tsodyks_markram_parameter_declares_its_role():
    fields = _reference_fields(TsodyksMarkramSynapticModel)

    assert fields, "expected the model to have reference fields"
    untagged = [name for name, extra in fields.items() if SchemaKey.REFERENCE_TAG not in extra]
    assert untagged == []


def test_the_config_answers_every_role_the_parameters_declare():
    # An unanswered tag falls back to the type-keyed label, which is the same string for all
    # nine of them - the exact thing tagging is here to avoid.
    tags = {
        extra[SchemaKey.REFERENCE_TAG]
        for extra in _reference_fields(TsodyksMarkramSynapticModel).values()
    }

    assert tags <= set(_config_tag_defaults())


def test_the_nine_parameters_get_nine_different_answers():
    # The point of keying by role rather than by reference type: all nine fields accept
    # AllDistributionsReference, so a type-keyed map could only ever offer them one answer.
    # Only the parameters are checked; several neuron set roles deliberately share a block.
    names = [_config_tag_defaults()[tag]["name"] for tag in TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS]

    assert len(names) == 9
    assert len(names) == len(set(names))


def test_each_answer_names_the_distribution_that_field_actually_falls_back_to():
    # Built from the same DistributionDefault objects `sample` resolves against, so this
    # fails if a default is changed in one place and not the other.
    for name, extra in _reference_fields(TsodyksMarkramSynapticModel).items():
        tag = extra[SchemaKey.REFERENCE_TAG]
        assert (
            _config_tag_defaults()[tag]["name"] == (extra[SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL])
        ), name


def test_both_concrete_models_carry_the_tags():
    for model_class in (
        ExcitatoryTsodyksMarkramSynapticModel,
        InhibitoryTsodyksMarkramSynapticModel,
    ):
        tags = {extra[SchemaKey.REFERENCE_TAG] for extra in _reference_fields(model_class).values()}
        assert tags == set(TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS)


def test_every_declared_tag_is_a_reference_tag_member():
    assert set(TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS) <= set(ReferenceTag)


def test_fields_without_a_default_are_left_untagged():
    # An assigner cannot run without a synaptic model or a neuron set, so those fields keep
    # their type-keyed label, which reads as the prompt it is rather than promising a default.
    labels = SynapseParameterizationScanConfig.json_schema_extra_additions[
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS
    ]

    assert "Select" in labels["SynapticModelReference"]


def test_each_answer_carries_the_block_behind_its_name():
    # The name and the block travel together so the UI can label the field and also read the
    # values behind that label - offering them in a tooltip, or materialising the default.
    for answer in _config_tag_defaults().values():
        assert set(answer) == {"name", "block"}
        assert isinstance(answer["name"], str)
        assert "type" in answer["block"]


def test_the_block_matches_the_distribution_the_field_falls_back_to():
    for tag, (_name, distribution) in tsodyks_markram_default_distributions().items():
        assert _config_tag_defaults()[tag]["block"] == json.loads(distribution.model_dump_json())
