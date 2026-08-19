from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from obi_one.scientific.blocks.distributions.base import Distribution


class DistributionReference(Protocol):
    """Protocol implemented by references to distribution blocks."""

    @property
    def block(self) -> Distribution:
        """The referenced distribution block."""


def describe_distribution(distribution: Distribution) -> str:
    """Return a concise description of a configured distribution."""
    parameters: list[str] = []
    omitted_fields = {"include_min", "include_max", "random_seed", "shift", "type"}
    for name, field in type(distribution).model_fields.items():
        if name in omitted_fields:
            continue
        value = getattr(distribution, name)
        if value is None:
            continue
        label = (field.title or name.replace("_", " ")).lower()
        parameters.append(f"{label}={value!r}")

    distribution_name = distribution.title or type(distribution).__name__
    if not parameters:
        return f"a {distribution_name} distribution"
    return f"a {distribution_name} distribution with {', '.join(parameters)}"


@dataclass(frozen=True)
class DistributionDefault:
    """Lazily created distribution fallback with a generated UI description."""

    factory: Callable[[], Distribution]

    def create(self) -> Distribution:
        """Create a fresh distribution instance for runtime sampling."""
        return self.factory()

    @property
    def description(self) -> str:
        """Describe the distribution produced by the fallback factory."""
        return describe_distribution(self.create())


def resolve_distribution(
    reference: DistributionReference | None,
    default: DistributionDefault,
) -> Distribution:
    """Resolve a reference or lazily create its distribution fallback."""
    return default.create() if reference is None else reference.block
