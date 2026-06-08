"""Rheobase-computation strategies for the extraction stage.

bluepyefe computes each cell's rheobase before matching recordings to target
amplitudes. Each strategy is a :class:`Block` carrying only its own parameters;
together they form :data:`RheobaseStrategyUnion`, rendered as a ``block_union``
so the user picks exactly one strategy and sees only its parameters.

:meth:`RheobaseStrategy.to_dict` returns the keyword arguments for the chosen
strategy's function in ``bluepyefe.rheobase`` (forwarded by BluePyEModel as
``rheobase_settings_extraction``); the ``strategy`` class variable is the name
forwarded as ``rheobase_strategy_extraction``. ``protocols`` (shared by every
strategy) lists the protocols whose recordings drive the rheobase search.
"""

from typing import Annotated, ClassVar

from pydantic import Discriminator, Field, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class RheobaseStrategy(Block):
    """Base class for rheobase strategies."""

    strategy: ClassVar[str]

    protocols: tuple[str, ...] = Field(
        default=("IDthresh",),
        title="Rheobase protocols",
        description="Protocols whose recordings are used to determine the rheobase.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    def to_dict(self) -> dict:  # noqa: PLR6301
        """Return the ``rheobase_settings`` kwargs for this strategy's function."""
        return {}


class AbsoluteRheobase(RheobaseStrategy):
    """Lowest amplitude inducing at least ``spike_threshold`` spikes."""

    strategy: ClassVar[str] = "absolute"

    spike_threshold: PositiveInt = Field(
        default=1,
        title="Spike threshold",
        description="Minimum number of spikes a recording must show to qualify as the rheobase.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {"spike_threshold": self.spike_threshold}


class FlushRheobase(RheobaseStrategy):
    """Lowest amplitude followed by ``flush_length`` further spiking sweeps."""

    strategy: ClassVar[str] = "flush"

    flush_length: PositiveInt = Field(
        default=1,
        title="Flush length",
        description="Number of subsequent sweeps that must also spike for an amplitude to qualify.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    upper_bound_spikecount: PositiveInt | None = Field(
        default=None,
        title="Upper bound spikecount",
        description=(
            "Stop searching once a recording exceeds this spike count. Leave empty for no bound."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        settings: dict = {"flush_length": self.flush_length}
        if self.upper_bound_spikecount is not None:
            settings["upper_bound_spikecount"] = self.upper_bound_spikecount
        return settings


class MajorityRheobase(RheobaseStrategy):
    """Lowest amplitude bin where a ``majority`` fraction of sweeps spike."""

    strategy: ClassVar[str] = "majority"

    min_step: PositiveFloat = Field(
        default=0.01,
        title="Minimum amplitude step",
        description="Width (nA) of the amplitude bins used to find the rheobase bin.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    majority: float = Field(
        default=0.5,
        title="Majority fraction",
        description="Fraction of sweeps in a bin that must spike for that bin to be the rheobase.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {"min_step": self.min_step, "majority": self.majority}


class InterpolationRheobase(RheobaseStrategy):
    """Interpolate the f-I curve to zero frequency (no parameters)."""

    strategy: ClassVar[str] = "interpolation"


# Discriminated union over the concrete strategies, keyed on the ``type`` literal
# stamped on each subclass by :class:`OBIBaseModel`. Rendered as a block_union.
RheobaseStrategyUnion = Annotated[
    AbsoluteRheobase | FlushRheobase | MajorityRheobase | InterpolationRheobase,
    Discriminator("type"),
]
