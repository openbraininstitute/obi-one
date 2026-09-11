import numpy as np
import pandas as pd

from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference

INDICES = pd.DataFrame(index=[0, 1, 2, 3])


def _distribution_reference(distribution):
    reference = AllDistributionsReference(block_dict_name="distributions", block_name="shared")
    reference.block = distribution
    return reference


def test_the_seed_changes_the_values():
    # The assigner offers `random_seed` as a swept parameter. Before the generator was
    # threaded through, every distribution seeded itself from its own `random_seed` (1 by
    # default), so every seed in a sweep produced an identical circuit.
    model = ExcitatoryTsodyksMarkramSynapticModel()

    first = model.sample(INDICES, rng=np.random.default_rng(1))
    second = model.sample(INDICES, rng=np.random.default_rng(2))

    assert first["facilitation_time"].tolist() != second["facilitation_time"].tolist()


def test_the_same_seed_reproduces_the_values():
    model = ExcitatoryTsodyksMarkramSynapticModel()

    first = model.sample(INDICES, rng=np.random.default_rng(7))
    second = model.sample(INDICES, rng=np.random.default_rng(7))

    assert first["facilitation_time"].tolist() == second["facilitation_time"].tolist()


def test_two_parameters_sharing_a_distribution_draw_independently():
    # Each parameter used to build its own generator from the distribution's seed, so two
    # parameters given the same distribution were perfectly correlated - every synapse got
    # the same facilitation and depression time.
    model = ExcitatoryTsodyksMarkramSynapticModel(
        facilitation_time=_distribution_reference(GammaDistribution(shape=4.0, scale=0.25)),
        depression_time=_distribution_reference(GammaDistribution(shape=4.0, scale=0.25)),
    )

    samples = model.sample(INDICES, rng=np.random.default_rng(1))

    assert samples["facilitation_time"].tolist() != samples["depression_time"].tolist()


def test_an_unset_generator_keeps_the_per_distribution_behaviour():
    # Callers that pass nothing are unaffected: each distribution still seeds itself, so
    # sampling stays deterministic for anything that relied on it.
    model = ExcitatoryTsodyksMarkramSynapticModel()

    assert model.sample(INDICES)["facilitation_time"].tolist() == (
        model.sample(INDICES)["facilitation_time"].tolist()
    )


def test_the_drawn_parameters_respond_to_the_seed_and_the_fixed_ones_do_not():
    model = ExcitatoryTsodyksMarkramSynapticModel()

    first = model.sample(INDICES, rng=np.random.default_rng(1))
    second = model.sample(INDICES, rng=np.random.default_rng(2))

    varying = {
        name
        for name in ExcitatoryTsodyksMarkramSynapticModel.parameter_names()
        if first[name].tolist() != second[name].tolist()
    }

    # syn_type_id is the model's identity rather than a draw, and two of the built-in
    # defaults are constant distributions, which have nothing to vary.
    assert "syn_type_id" not in varying
    assert "u_hill_coefficient" not in varying
    assert "conductance_scale_factor" not in varying
    assert {"facilitation_time", "depression_time", "decay_time", "u_syn", "delay"} <= varying
