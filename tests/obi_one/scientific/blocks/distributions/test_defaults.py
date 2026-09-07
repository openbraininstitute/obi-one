from types import SimpleNamespace
from typing import ClassVar

from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    describe_distribution,
    resolve_distribution,
)


class _EmptyDistribution(Distribution):
    title: ClassVar[str] = "Empty"

    def _sample_generator(self, n=1, _rng=None):
        return [0.0] * n


class _ConfiguredDistribution(Distribution):
    title: ClassVar[str] = "Configured"
    value: float = 1.5

    def _sample_generator(self, n=1, _rng=None):
        return [self.value] * n


def test_describe_distribution_without_configured_parameters():
    assert describe_distribution(_EmptyDistribution()) == "a Empty distribution"


def test_describe_distribution_falls_back_to_field_name():
    assert describe_distribution(_ConfiguredDistribution()) == (
        "a Configured distribution with value=1.5"
    )


def test_describe_distribution_uses_field_title():
    assert describe_distribution(FloatConstantDistribution(value=1.5)) == (
        "a Constant Float distribution with value=1.5"
    )


def test_distribution_default_is_lazy_and_resolves_references():
    created = []

    def factory():
        created.append(True)
        return _EmptyDistribution()

    default = DistributionDefault(factory)
    first = default.create()
    second = default.create()

    assert first is not second
    assert len(created) == 2
    assert default.description == "a Empty distribution"
    assert default.label == "Built-in default: Empty distribution"

    explicit = _ConfiguredDistribution()
    reference = SimpleNamespace(block=explicit)
    assert isinstance(resolve_distribution(None, default), _EmptyDistribution)
    assert resolve_distribution(reference, default) is explicit
