from obi_one.core.fill_none_references import fill_none_references_in_config
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationScanConfig,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag


def _defaults():
    return SynapseParameterizationScanConfig.default_block_references()


def _config_with(model):
    """Enough of a config for the fill pass: it walks blocks and block dictionaries."""

    class _Config:
        def __init__(self):
            self.synaptic_models = {"model": model}
            self.distributions = {}

    return _Config()


def _named_reference(distribution, name="explicit"):
    reference = AllDistributionsReference(block_dict_name="distributions", block_name=name)
    reference.block = distribution
    return reference


def test_every_unset_parameter_is_given_a_reference():
    model = ExcitatoryTsodyksMarkramSynapticModel()
    config = _config_with(model)

    fill_none_references_in_config(config, _defaults())

    unset = [
        name
        for name in ("facilitation_time", "depression_time", "u_syn", "delay_distribution")
        if getattr(model, name) is None
    ]
    assert unset == []


def test_the_reference_points_at_the_distribution_the_field_falls_back_to():
    model = ExcitatoryTsodyksMarkramSynapticModel()

    fill_none_references_in_config(_config_with(model), _defaults())

    # The block name is the label the UI showed for that field, so the option a user saw and
    # the block that now exists read alike.
    assert (
        model.facilitation_time.block_name
        == (
            SynapseParameterizationScanConfig.json_schema_extra_additions["reference_tag_defaults"][
                ReferenceTag.FACILITATION_TIME_DISTRIBUTION
            ]
        )
    )


def test_a_parameter_the_user_set_is_left_alone():
    chosen = _named_reference(FloatConstantDistribution(value=3.5))
    model = ExcitatoryTsodyksMarkramSynapticModel(facilitation_time=chosen)

    fill_none_references_in_config(_config_with(model), _defaults())

    assert model.facilitation_time is chosen


def test_only_the_defaults_actually_needed_are_returned():
    # A config that names every parameter itself should gain no distributions it never
    # refers to, which is what the returned list is for.
    explicit = {
        name: _named_reference(FloatConstantDistribution(value=1.0), name)
        for name in (
            "u_hill_coefficient_distribution",
            "conductance_distribution",
            "conductance_scale_factor_distribution",
            "facilitation_time",
            "depression_time",
            "n_rrp_vesicles_distribution",
            "decay_time",
            "u_syn",
            "delay_distribution",
        )
    }
    model = ExcitatoryTsodyksMarkramSynapticModel(**explicit)

    used = fill_none_references_in_config(_config_with(model), _defaults())

    assert used == []


def test_a_default_needed_twice_is_returned_once():
    # Two models both leaving the same parameter unset share one block rather than
    # registering two identical distributions under the same name.
    config = _config_with(ExcitatoryTsodyksMarkramSynapticModel())
    config.synaptic_models["second"] = ExcitatoryTsodyksMarkramSynapticModel()

    used = fill_none_references_in_config(config, _defaults())

    names = [reference.block_name for reference in used]
    assert len(names) == len(set(names))


def test_the_defaults_cover_every_tagged_parameter():
    tags = set(_defaults())
    model_tags = {
        field.json_schema_extra["reference_tag"]
        for field in ExcitatoryTsodyksMarkramSynapticModel.model_fields.values()
        if isinstance(field.json_schema_extra, dict) and "reference_tag" in field.json_schema_extra
    }

    assert model_tags <= tags
