"""The range a sampled parameter is allowed to take, and the clip onto it.

Nothing here is particular to one synaptic model: a domain is a property of the parameter, and
any model that samples values can declare one. The ranges themselves are declared on the fields
they constrain, under `SchemaKey.PARAMETER_DOMAIN`; this module holds only the shape they take
and the clip.

That clip runs on the values a distribution drew, not on what the user configured - the field
holds a reference to a distribution, so pydantic never sees these numbers.

A drawn value outside the range is pulled onto it rather than raising. A distribution knows
nothing about the parameter it was chosen for, so a Normal picked for a positive time will draw
negative values from its tail however sensible its mean and standard deviation are; failing the
run for that would make most distributions unusable for most parameters. The clip is a property
of the *model*, which cannot represent a negative facilitation time, rather than a judgement
about the distribution.
"""

import logging
from math import ceil, floor, inf, isfinite, isinf, isnan, nextafter
from typing import NamedTuple

L = logging.getLogger(__name__)

_EXAMPLES_IN_MESSAGE = 3


class ParameterDomain(NamedTuple):
    minimum: float | None = None
    maximum: float | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    integer: bool = False
    description: str = ""


def is_valid_parameter_sample(sample: float, domain: ParameterDomain) -> bool:
    value = float(sample)
    valid = isfinite(value)
    if valid and domain.integer:
        valid = value.is_integer()
    if valid and domain.minimum is not None:
        valid = value >= domain.minimum if domain.minimum_inclusive else value > domain.minimum
    if valid and domain.maximum is not None:
        valid = value <= domain.maximum if domain.maximum_inclusive else value < domain.maximum
    return valid


def lowest_allowed(domain: ParameterDomain) -> float | None:
    """The smallest value the domain admits, or None if it is unbounded below.

    `nextafter` rather than a fixed epsilon for an exclusive bound: it is the next representable
    float, so it satisfies the bound whatever its magnitude. Adding 1e-9 to a bound of 1e12
    lands back on the bound itself.
    """
    if domain.minimum is None:
        return None
    if domain.integer:
        # The smallest integer strictly above an exclusive bound is one past its floor; the
        # smallest at or above an inclusive one is its ceiling.
        return (
            float(floor(domain.minimum) + 1)
            if not domain.minimum_inclusive
            else float(ceil(domain.minimum))
        )
    return domain.minimum if domain.minimum_inclusive else nextafter(domain.minimum, inf)


def highest_allowed(domain: ParameterDomain) -> float | None:
    """The largest value the domain admits, or None if it is unbounded above."""
    if domain.maximum is None:
        return None
    if domain.integer:
        return (
            float(ceil(domain.maximum) - 1)
            if not domain.maximum_inclusive
            else float(floor(domain.maximum))
        )
    return domain.maximum if domain.maximum_inclusive else nextafter(domain.maximum, -inf)


def clip_parameter_samples(
    parameter_name: str,
    domain: ParameterDomain,
    samples: list[float],
    sampled_by: str = "",
) -> list[float]:
    """Pull every drawn value onto the range that parameter is allowed to take.

    Values below the minimum become the minimum, values above the maximum become the maximum,
    and an integer domain rounds first so that the bound has the last word. Clipping is logged,
    not silent: a distribution most of whose draws are being clipped is a badly chosen one, and
    the run should say so even though it continues.

    The one thing that is not clipped is a value with nowhere to be clipped *to* - a NaN, which
    has no position on the line at all, and an infinity in a direction the domain does not
    bound. Both mean the distribution is broken rather than merely ill-suited, and substituting
    a number for them would put invented values into the circuit with nothing recording it.

    `sampled_by` names the model that drew them, since a config can hold several and the
    parameter name alone would not say which one produced the offending values.
    """
    low = lowest_allowed(domain)
    high = highest_allowed(domain)
    source = f"{sampled_by} " if sampled_by else ""

    def unusable(value: float) -> bool:
        """Whether there is nowhere to clip this value to.

        An infinity is clippable when the domain bounds it on its *own* side: -inf onto a
        minimum, +inf onto a maximum. Most domains here bound only one side, so which side the
        infinity is on decides it.
        """
        if isnan(value):
            return True
        if isinf(value):
            return high is None if value > 0 else low is None
        return False

    def clip_one(sample: float) -> float:
        value = float(sample)
        if unusable(value):
            msg = (
                f"Unusable value sampled for {source}parameter {parameter_name!r}: "
                f"expected {domain.description}; got {value!r}, which cannot be clipped onto "
                f"that range."
            )
            raise ValueError(msg)
        if domain.integer and isfinite(value):
            value = float(round(value))
        if low is not None and value < low:
            return low
        if high is not None and value > high:
            return high
        return value

    clipped = [clip_one(sample) for sample in samples]

    # Asked as "was it outside the domain", not "did the number change": the two are the same
    # question here, and this one needs no float equality comparison to answer.
    changed = [
        (float(before), after)
        for before, after in zip(samples, clipped, strict=True)
        if not is_valid_parameter_sample(before, domain)
    ]
    if changed:
        L.warning(
            "Clipped %d of %d values sampled for %sparameter %r onto %s. First %d: %s.",
            len(changed),
            len(samples),
            source,
            parameter_name,
            domain.description or "its domain",
            min(len(changed), _EXAMPLES_IN_MESSAGE),
            ", ".join(
                f"{before!r} -> {after!r}" for before, after in changed[:_EXAMPLES_IN_MESSAGE]
            ),
        )

    return clipped
