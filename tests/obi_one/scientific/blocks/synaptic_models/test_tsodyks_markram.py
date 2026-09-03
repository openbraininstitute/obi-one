import pandas as pd
import pytest

from obi_one.scientific.blocks.distributions.constant import (
    FloatConstantDistribution,
    IntConstantDistribution,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference


def _distribution_reference(distribution):
    reference = AllDistributionsReference(
        block_dict_name="distributions", block_name="test_distribution"
    )
    reference.block = distribution
    return reference


@pytest.mark.parametrize(
    "model_class",
    [ExcitatoryTsodyksMarkramSynapticModel, InhibitoryTsodyksMarkramSynapticModel],
)
def test_default_sampling_preserves_index_schema_and_model_type(model_class):
    model = model_class()
    indices = pd.DataFrame(index=[101, 205])

    samples = model.sample(indices)

    assert samples.index.equals(indices.index)
    assert list(samples.columns) == model.parameter_names()
    assert samples["syn_type_id"].eq(model.syn_type_id).all()


def test_sampling_uses_explicit_distributions_and_preserves_values():
    model = ExcitatoryTsodyksMarkramSynapticModel(
        u_hill_coefficient_distribution=_distribution_reference(
            FloatConstantDistribution(value=2.0)
        ),
        conductance_distribution=_distribution_reference(FloatConstantDistribution(value=0.25)),
        conductance_scale_factor_distribution=_distribution_reference(
            FloatConstantDistribution(value=0.5)
        ),
        fascilitation_time=_distribution_reference(FloatConstantDistribution(value=10.0)),
        depression_time=_distribution_reference(FloatConstantDistribution(value=20.0)),
        n_rrp_vesicles_distribution=_distribution_reference(IntConstantDistribution(value=4)),
        decay_time=_distribution_reference(FloatConstantDistribution(value=1.8)),
        u_syn=_distribution_reference(FloatConstantDistribution(value=0.5)),
        delay_distribution=_distribution_reference(FloatConstantDistribution(value=1.0)),
    )
    indices = pd.DataFrame(index=[11, 23])

    samples = model.sample(indices)

    assert samples.index.equals(indices.index)
    assert samples[
        [
            "u_hill_coefficient",
            "conductance",
            "conductance_scale_factor",
            "facilitation_time",
            "depression_time",
            "n_rrp_vesicles",
            "decay_time",
            "u_syn",
            "delay",
        ]
    ].to_dict(orient="list") == {
        "u_hill_coefficient": [2.0, 2.0],
        "conductance": [0.25, 0.25],
        "conductance_scale_factor": [0.5, 0.5],
        "facilitation_time": [10.0, 10.0],
        "depression_time": [20.0, 20.0],
        "n_rrp_vesicles": [4.0, 4.0],
        "decay_time": [1.8, 1.8],
        "u_syn": [0.5, 0.5],
        "delay": [1.0, 1.0],
    }
    assert samples["syn_type_id"].eq(model.syn_type_id).all()


@pytest.mark.parametrize(
    ("distribution_field", "parameter_name", "sample"),
    [
        ("u_hill_coefficient_distribution", "u_hill_coefficient", 0.0),
        ("conductance_distribution", "conductance", -0.1),
        ("conductance_scale_factor_distribution", "conductance_scale_factor", 0.0),
        ("fascilitation_time", "facilitation_time", 0.0),
        ("depression_time", "depression_time", 0.0),
        ("n_rrp_vesicles_distribution", "n_rrp_vesicles", 1.5),
        ("decay_time", "decay_time", 0.0),
        ("u_syn", "u_syn", 1.1),
        ("delay_distribution", "delay", -0.1),
        ("conductance_distribution", "conductance", float("nan")),
    ],
)
def test_sampling_rejects_invalid_explicit_distribution_values(
    distribution_field, parameter_name, sample
):
    model = ExcitatoryTsodyksMarkramSynapticModel(
        **{distribution_field: _distribution_reference(FloatConstantDistribution(value=sample))}
    )

    with pytest.raises(ValueError, match=parameter_name):
        model.sample(pd.DataFrame(index=[0]))


@pytest.mark.parametrize(
    ("distribution_field", "parameter_name", "sample"),
    [
        ("u_hill_coefficient_distribution", "u_hill_coefficient", 1.0),
        ("conductance_distribution", "conductance", 0.0),
        ("n_rrp_vesicles_distribution", "n_rrp_vesicles", 1.0),
        ("u_syn", "u_syn", 0.0),
        ("u_syn", "u_syn", 1.0),
    ],
)
def test_sampling_accepts_valid_parameter_boundaries(distribution_field, parameter_name, sample):
    model = ExcitatoryTsodyksMarkramSynapticModel(
        **{distribution_field: _distribution_reference(FloatConstantDistribution(value=sample))}
    )

    samples = model.sample(pd.DataFrame(index=[0]))

    assert samples[parameter_name].tolist() == [sample]
