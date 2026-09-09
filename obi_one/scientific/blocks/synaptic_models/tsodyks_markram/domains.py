"""The range each Tsodyks-Markram parameter is allowed to take, and the check against it.

Separate from the distributions that supply the values: this file says what a parameter may
be, `distributions.py` what it is when nobody chooses. The two are held in agreement by
`test_parameter_domains`, which draws from every built-in default and checks it here.
"""

import logging
from math import isfinite
from typing import NamedTuple

L = logging.getLogger(__name__)


class _ParameterDomain(NamedTuple):
    minimum: float | None = None
    maximum: float | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    integer: bool = False
    description: str = ""


_TM_PARAMETER_DOMAINS: dict[str, _ParameterDomain] = {
    "u_hill_coefficient": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive finite value",
    ),
    "conductance": _ParameterDomain(
        minimum=0.0,
        description="a non-negative finite value",
    ),
    "conductance_scale_factor": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive finite value",
    ),
    "facilitation_time": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive time in milliseconds",
    ),
    "depression_time": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive time in milliseconds",
    ),
    "n_rrp_vesicles": _ParameterDomain(
        minimum=1.0,
        integer=True,
        description="an integer value greater than or equal to 1",
    ),
    "decay_time": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive time in milliseconds",
    ),
    "u_syn": _ParameterDomain(
        minimum=0.0,
        maximum=1.0,
        description="a finite value between 0 and 1",
    ),
    "delay": _ParameterDomain(
        minimum=0.0,
        description="a non-negative time in milliseconds",
    ),
}


def _is_valid_parameter_sample(sample: float, domain: _ParameterDomain) -> bool:
    value = float(sample)
    valid = isfinite(value)
    if valid and domain.integer:
        valid = value.is_integer()
    if valid and domain.minimum is not None:
        valid = value >= domain.minimum if domain.minimum_inclusive else value > domain.minimum
    if valid and domain.maximum is not None:
        valid = value <= domain.maximum if domain.maximum_inclusive else value < domain.maximum
    return valid


def _validate_parameter_samples(parameter_name: str, samples: list[float]) -> list[float]:
    domain = _TM_PARAMETER_DOMAINS[parameter_name]
    invalid_samples = [
        sample for sample in samples if not _is_valid_parameter_sample(sample, domain)
    ]

    if invalid_samples:
        msg = (
            f"Invalid values sampled for Tsodyks-Markram parameter {parameter_name!r}: "
            f"expected {domain.description}; got {invalid_samples[:3]!r}."
        )
        raise ValueError(msg)

    return samples
