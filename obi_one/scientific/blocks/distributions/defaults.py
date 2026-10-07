"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.distributions.defaults import (
    Callable,
    dataclass,
    describe_distribution,
    Distribution,
    DistributionDefault,
    DistributionReference,
    Protocol,
    resolve_distribution,
)

__all__ = [
    "Callable",
    "dataclass",
    "describe_distribution",
    "Distribution",
    "DistributionDefault",
    "DistributionReference",
    "Protocol",
    "resolve_distribution",
]
