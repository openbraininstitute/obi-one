"""The range a sampled parameter is allowed to take, and the check against it.

Nothing here is particular to one synaptic model: a domain is a property of the parameter, and
any model that samples values can declare one. The ranges themselves are declared on the fields
they constrain, under `SchemaKey.PARAMETER_DOMAIN`; this module holds only the shape they take
and the check.

That check runs on the values a distribution drew, not on what the user configured - the field
holds a reference to a distribution, so pydantic never sees these numbers.
"""

import logging
from math import isfinite
from typing import NamedTuple

L = logging.getLogger(__name__)


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


def validate_parameter_samples(
    parameter_name: str,
    domain: ParameterDomain,
    samples: list[float],
    sampled_by: str = "",
) -> list[float]:
    """Reject any drawn value outside the range that parameter is allowed to take.

    `sampled_by` names the model that drew them, since a config can hold several and the
    parameter name alone would not say which one produced the offending values.
    """
    invalid_samples = [
        sample for sample in samples if not is_valid_parameter_sample(sample, domain)
    ]

    if invalid_samples:
        source = f"{sampled_by} " if sampled_by else ""
        msg = (
            f"Invalid values sampled for {source}parameter {parameter_name!r}: "
            f"expected {domain.description}; got {invalid_samples[:3]!r}."
        )
        raise ValueError(msg)

    return samples
