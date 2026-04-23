"""Brian2-specific direct-injection Poisson stimulus block.

Drives each neuron in ``neuron_set`` with its own independent Poisson spike
train, kicking the target membrane potential directly — equivalent to one
``brian2.PoissonInput`` per target neuron.

Unlike :class:`PoissonSpikeStimulus`, which emits a SONATA ``synapse_replay``
entry backed by a pre-generated spike file and propagates the replayed spikes
through the circuit's *existing* synapses, this block emits a SONATA ``poisson``
input module (non-standard) and bypasses the circuit's synapses entirely. Only
``Brian2SimulationFromSonataTask`` understands the ``poisson`` module, via its
``Brian2PoissonInput`` handler.
"""

from typing import Annotated, ClassVar

from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_NON_NEGATIVE_FLOAT_VALUE,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference


class Brian2DirectPoissonStimulus(Block):
    """Independent Poisson drive injected directly into target membrane potentials.

    Emitted as a SONATA ``inputs`` entry with ``module="poisson"``. Every
    neuron in :attr:`neuron_set` receives its own ``PoissonInput`` firing at
    :attr:`frequency`; each spike adds :attr:`weight` to the target state
    variable (default ``v``). If :attr:`zero_refractory` is true, the
    targeted neurons' refractory period (state variable ``rfc``) is cleared
    so they can follow the Poisson rate.
    """

    title: ClassVar[str] = "Direct Poisson Input (Brian2)"

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set",
        description="Neurons that receive the Poisson drive.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: False,
        },
    )

    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=150.0,
        title="Frequency",
        description="Mean Poisson rate (Hz) driving each target neuron.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    weight: float | list[float] = Field(
        default=1.0e-3,
        title="Weight",
        description="Amplitude of each Poisson kick, in volts (SI).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    target_var: str | list[str] = Field(
        default="v",
        title="Target Variable",
        description="Brian2 neuron state variable that each Poisson kick increments.",
    )

    zero_refractory: bool | list[bool] = Field(
        default=True,
        title="Zero Refractory",
        description=(
            "If true, clear the neuron group's 'rfc' refractory state variable on "
            "targeted neurons so they can follow the Poisson rate."
        ),
    )

    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description=(
            "Informational only; Brian2 PoissonInput is always-on for the whole "
            "simulation. Recorded in the SONATA entry for forward compatibility."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    _default_node_set: str = PrivateAttr(default="All")

    def config(
        self,
        circuit: Circuit,  # noqa: ARG002
        population: str | None = None,  # noqa: ARG002
        default_node_set: str = "All",
        default_timestamps: TimestampsReference | None = None,
    ) -> dict:
        """Return the SONATA inputs entry for this block.

        The biophysical check that :class:`ContinuousStimulusWithoutTimestamps`
        applies is deliberately skipped: this stimulus injects directly into
        ``v`` (or any target variable) and is valid for point-neuron and
        biophysical populations alike.
        """
        self._default_node_set = default_node_set
        _ = default_timestamps or SingleTimestamp(start_time=0.0)
        return self._generate_config()

    def _generate_config(self) -> dict:
        return {
            self.block_name: {
                "input_type": "spikes",
                "module": "poisson",
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "rate": self.frequency,
                "weight": self.weight,
                "target_var": self.target_var,
                "zero_refractory": self.zero_refractory,
                "duration": self.duration,
            }
        }
