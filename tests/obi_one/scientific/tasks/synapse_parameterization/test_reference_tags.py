import json

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)
from obi_one.scientific.tasks.circuit_extraction.task import (
    CircuitExtractionScanConfig,
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


def _parameter_tags():
    """The roles the Tsodyks-Markram parameters play, read off the fields that declare them."""
    return {
        extra[SchemaKey.REFERENCE_TAG]
        for extra in _reference_fields(TsodyksMarkramSynapticModel).values()
    }


def _config_tag_defaults():
    """What the config publishes: derived by the base, not written out by the config."""
    return SynapseParameterizationScanConfig.model_config["json_schema_extra"][
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
    names = [_config_tag_defaults()[tag]["name"] for tag in _parameter_tags()]

    assert len(names) == 9
    assert len(names) == len(set(names))


def test_each_answer_names_the_distribution_that_field_actually_falls_back_to():
    """The config's answer and the block's own fallback must be the same distribution.

    The block no longer describes its defaults - the config declares them and the schema
    publishes them - so nothing but this holds the two ends together. `_default_distributions`
    is what `sample` resolves against when a field is left unset.
    """
    fallbacks = TsodyksMarkramSynapticModel._default_distributions
    for field_name, extra in _reference_fields(TsodyksMarkramSynapticModel).items():
        tag = extra[SchemaKey.REFERENCE_TAG]
        assert _config_tag_defaults()[tag]["name"] == fallbacks[field_name].label, field_name


def test_both_concrete_models_carry_the_tags():
    for model_class in (
        ExcitatoryTsodyksMarkramSynapticModel,
        InhibitoryTsodyksMarkramSynapticModel,
    ):
        tags = {extra[SchemaKey.REFERENCE_TAG] for extra in _reference_fields(model_class).values()}
        assert tags == _parameter_tags()


def test_every_declared_tag_is_a_reference_tag_member():
    assert _parameter_tags() <= set(ReferenceTag)


def test_the_config_declares_no_type_keyed_labels():
    """Every reference field here is tagged and answered, so the type-keyed map is dead weight.

    It is keyed by reference type, so it could only ever give every field accepting
    AllDistributionsReference the same answer - which is what it did, for nine parameters with
    nine different defaults. Dropping it is safe only because the UI now shows a field once its
    role is answered, rather than only when its type is labelled.
    """
    assert (
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS
        not in SynapseParameterizationScanConfig.json_schema_extra_additions
    )


def test_each_answer_carries_the_block_behind_its_name():
    # The name and the block travel together so the UI can label the field and also read the
    # values behind that label - offering them in a tooltip, or materialising the default.
    for answer in _config_tag_defaults().values():
        assert set(answer) == {"name", "block"}
        assert isinstance(answer["name"], str)
        assert "type" in answer["block"]


def test_the_block_matches_the_distribution_the_field_falls_back_to():
    for tag, (
        _name,
        distribution,
    ) in TsodyksMarkramSynapticModel.default_distributions_by_role().items():
        assert _config_tag_defaults()[tag]["block"] == json.loads(distribution.model_dump_json())


def test_the_schema_is_derived_from_the_declared_defaults():
    """The schema the UI reads must name exactly what the fill will substitute.

    These were written out separately once, and drifted: the schema named nine roles while the
    fill answered seventeen, and nothing failed. `ScanConfig.__init_subclass__` now derives one
    from the other, so a config declaring a default cannot forget to publish it.
    """
    declared = SynapseParameterizationScanConfig.default_block_references()
    published = _config_tag_defaults()

    assert set(published) == set(declared)
    for tag, reference in declared.items():
        assert published[tag]["name"] == reference.block_name
        assert published[tag]["block"] == json.loads(reference.block.model_dump_json())


def test_a_config_declaring_no_defaults_publishes_nothing():
    assert CircuitExtractionScanConfig.default_block_references() == {}
    assert (
        SchemaKey.REFERENCE_TAG_DEFAULTS
        not in CircuitExtractionScanConfig.model_config["json_schema_extra"]
    )


def test_a_config_declares_the_spec_and_the_base_resolves_it():
    """A config says what its defaults are; it says nothing about how they are used.

    `default_block_references` and the schema entry are both derived from `default_blocks`, so
    adopting this pattern is one method returning one mapping - not three that can disagree.
    """
    declared = SynapseParameterizationScanConfig.default_blocks()
    resolved = SynapseParameterizationScanConfig.default_block_references()

    assert set(resolved) == set(declared)
    for tag, block_default in declared.items():
        reference = resolved[tag]
        assert isinstance(reference, block_default.reference_type)
        assert reference.block_dict_name == block_default.block_dict_name
        assert reference.block_name == block_default.name
        assert reference.block.block_name == block_default.name


def test_each_resolution_builds_a_fresh_block():
    # Two configs must not share a block instance; the spec holds a factory for this reason.
    first = SynapseParameterizationScanConfig.default_block_references()
    second = SynapseParameterizationScanConfig.default_block_references()

    for tag, reference in first.items():
        assert reference.block is not second[tag].block
