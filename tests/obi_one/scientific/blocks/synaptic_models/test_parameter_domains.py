"""Each built-in default must produce values its own parameter is allowed to take.

The domain is declared on the field, the default supplies that field, and nothing but this
test holds the two in agreement - which is why it draws rather than reasons: a Gamma or Normal
default is only wrong for its domain some of the time.
"""

import logging

import numpy as np
import pytest

from obi_one.scientific.blocks.synaptic_models.domains import (
    ParameterDomain,
    clip_parameter_samples,
    highest_allowed,
    is_valid_parameter_sample,
    lowest_allowed,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)


def test_every_sampled_parameter_declares_a_domain_and_a_default():
    # The domains are shared - a parameter's range does not depend on the synapse being
    # excitatory or inhibitory - while the defaults are per model, since the values do.
    fields = TsodyksMarkramSynapticModel._sampled_fields()

    # syn_type_id is the model's identity rather than a draw, so it declares neither.
    assert [p for p, _d in fields.values()] + ["syn_type_id"] == (
        ExcitatoryTsodyksMarkramSynapticModel.parameter_names()
    )
    for model_class in (
        ExcitatoryTsodyksMarkramSynapticModel,
        InhibitoryTsodyksMarkramSynapticModel,
    ):
        assert set(fields) == set(model_class._defaults_by_field()), model_class.__name__


def test_a_domain_says_what_it_expects():
    # The description is quoted back in the warning a clipped draw logs, so an empty one
    # would produce "onto ; got [...]".
    for field, (_parameter, domain) in TsodyksMarkramSynapticModel._sampled_fields().items():
        assert domain.description, field


def test_the_built_in_defaults_stay_inside_their_own_domains():
    """Drawn rather than reasoned about: a Gamma or Normal is only wrong for its domain sometimes.

    Taken from each default distribution directly rather than through `sample`, which clips - a
    default that needed clipping would otherwise be indistinguishable from one that did not, and
    this test would pass no matter how badly matched a default was.
    """
    rng = np.random.default_rng(0)
    for model_class in (
        ExcitatoryTsodyksMarkramSynapticModel,
        InhibitoryTsodyksMarkramSynapticModel,
    ):
        defaults = model_class._defaults_by_field()
        for field, (parameter, domain) in model_class._sampled_fields().items():
            drawn = defaults[field].create().sample_with_constraints(2000, rng=rng)
            offending = [v for v in drawn if not is_valid_parameter_sample(v, domain)]
            assert offending == [], (
                f"{model_class.__name__}.{parameter}: {offending[:3]} outside {domain.description}"
            )


def test_the_two_models_can_differ_and_do():
    """Excitatory and inhibitory declare their own values, and at least one already differs.

    If this ever passes trivially - because every inhibitory value was copied from the
    excitatory one - the split has stopped earning its keep.
    """
    excitatory = ExcitatoryTsodyksMarkramSynapticModel._defaults_by_field()
    inhibitory = InhibitoryTsodyksMarkramSynapticModel._defaults_by_field()

    assert set(excitatory) == set(inhibitory)
    differing = [f for f in excitatory if excitatory[f].label != inhibitory[f].label]
    assert differing, "the two models declare identical defaults for every parameter"


# --- clipping -----------------------------------------------------------------------------
#
# A distribution knows nothing about the parameter it was chosen for, so a Normal picked for a
# positive time draws negative values from its tail. Those used to fail the run; they are now
# pulled onto the domain, because the constraint belongs to the model rather than to the
# distribution the user chose.

POSITIVE = ParameterDomain(minimum=0.0, minimum_inclusive=False, description="positive")
UNIT = ParameterDomain(minimum=0.0, maximum=1.0, description="between 0 and 1")
COUNT = ParameterDomain(minimum=1.0, integer=True, description="an integer of at least 1")


def test_a_value_inside_the_domain_is_returned_unchanged():
    assert clip_parameter_samples("p", UNIT, [0.0, 0.25, 1.0]) == [0.0, 0.25, 1.0]


def test_values_outside_are_pulled_onto_the_edge_rather_than_raising():
    assert clip_parameter_samples("p", UNIT, [-3.0, 1.7]) == [0.0, 1.0]


def test_an_integer_domain_rounds_then_clips():
    # Rounds first so the bound has the last word: 0.2 rounds to 0, which the minimum then
    # lifts to 1, rather than a rounded value escaping the range.
    assert clip_parameter_samples("p", COUNT, [0.2, 2.4, 2.6]) == [1.0, 2.0, 3.0]


def test_an_exclusive_bound_clips_to_a_value_that_satisfies_it():
    # Not to the bound itself, which the domain excludes.
    (clipped,) = clip_parameter_samples("p", POSITIVE, [-1.0])

    assert clipped > 0.0
    assert is_valid_parameter_sample(clipped, POSITIVE)


def test_an_exclusive_bound_is_respected_whatever_its_magnitude():
    """A fixed epsilon would vanish here: 1e12 + 1e-9 == 1e12 in floating point."""
    large = ParameterDomain(minimum=1e12, minimum_inclusive=False, description="large")

    (clipped,) = clip_parameter_samples("p", large, [0.0])

    assert clipped > 1e12


def test_the_integer_bounds_land_on_integers():
    assert lowest_allowed(COUNT) == pytest.approx(1.0)
    assert highest_allowed(COUNT) is None
    assert lowest_allowed(ParameterDomain(minimum=0.5, integer=True)) == pytest.approx(1.0)
    assert lowest_allowed(
        ParameterDomain(minimum=1.0, minimum_inclusive=False, integer=True)
    ) == pytest.approx(2.0)


def test_an_unbounded_side_clips_nothing_on_that_side():
    assert clip_parameter_samples("p", POSITIVE, [1e300]) == [1e300]


def test_clipping_is_reported():
    # A distribution most of whose draws are clipped is a badly chosen one; the run continues
    # but must not do so silently.
    logger = logging.getLogger("obi_one.scientific.blocks.synaptic_models.domains")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger.addHandler(handler)
    try:
        clip_parameter_samples("facilitation_time", UNIT, [-1.0, 0.5], sampled_by="SomeModel")
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    message = records[0].getMessage()
    assert "facilitation_time" in message
    assert "SomeModel" in message
    assert "1 of 2" in message


def test_nothing_inside_the_domain_is_reported():
    logger = logging.getLogger("obi_one.scientific.blocks.synaptic_models.domains")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger.addHandler(handler)
    try:
        clip_parameter_samples("p", UNIT, [0.0, 0.5, 1.0])
    finally:
        logger.removeHandler(handler)

    assert records == []


def test_a_value_with_nowhere_to_be_clipped_to_still_raises():
    """NaN has no position on the line, and +inf has no edge to meet without a maximum.

    These mean the distribution is broken rather than merely ill-suited to the parameter, and
    substituting a number would put an invented value into the circuit with nothing recording
    it.
    """
    for value in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="cannot be clipped"):
            clip_parameter_samples("p", POSITIVE, [value])


def test_an_infinity_the_domain_bounds_is_clipped_like_any_other_value():
    assert clip_parameter_samples("p", UNIT, [float("inf"), float("-inf")]) == [1.0, 0.0]
    assert clip_parameter_samples("p", POSITIVE, [float("-inf")])[0] > 0.0
