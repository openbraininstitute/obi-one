"""Brian2-specific direct-injection Poisson stimulus block.

Drives each neuron in ``neuron_set`` with its own independent Poisson spike
train, kicking the target membrane potential directly — equivalent to one
``brian2.PoissonInput`` per target neuron.

Unlike :class:`PoissonSpikeStimulus`, which emits a SONATA ``synapse_replay``
entry backed by a pre-generated spike file and propagates the replayed spikes
through the circuit's *existing* synapses, this block emits a SONATA ``poisson``
input module (non-standard) and bypasses the circuit's synapses entirely. The
SONATA -> Brian2 runner
``obi_one/scientific/library/simulation/brian2/simulate_brian2.py``
(``run_sonata_brian2_trial``) understands the ``poisson`` module.
"""

from typing import Annotated, ClassVar

from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    MIN_NON_NEGATIVE_FLOAT_VALUE,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_neuron_set,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference


class Brian2DirectPoissonStimulus(Block):
    """Independent Poisson drive injected directly into the soma.

    Each neuron receives its own Poisson Input directly into the soma
    firing. Each spike adds a weight to the membrane potential.
    """

    title: ClassVar[str] = "Direct Poisson Input"

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
        Annotated[NonNegativeFloat, Field(ge=MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=MIN_NON_NEGATIVE_FLOAT_VALUE)]]
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

    duration: (
        Annotated[NonNegativeFloat, Field(le=MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
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
        circuit: Circuit,
        population: str | None = None,
        default_node_set: str = "sugar",
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

        if self.neuron_set.block_name != "Default: All Biophysical Neurons":  # Temp hack
            neuron_set = resolve_neuron_set_ref_to_neuron_set(
                self.neuron_set, self._default_node_set
            )
            max_n_neurons = 100
            if (
                len(neuron_set.get_neuron_ids(circuit=circuit, population=population))
                > max_n_neurons
            ):
                msg = (
                    f"Number of neurons used with the {self.title} exceeds the maximum "
                    f"allowed: {max_n_neurons}."
                )
                raise ValueError(msg)

        return self._generate_config()

    def _generate_config(self) -> dict:

        if self.neuron_set.block_name == "Default: All Biophysical Neurons":
            node_set = "sugar"
        else:
            node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set)

        return {
            self.block_name: {
                "input_type": "spikes",
                "module": "poisson",
                "node_set": node_set,
                "rate": self.frequency,
                "weight": self.weight,
                # libsonata requires `delay` on every input; the Brian2
                # PoissonInput is always-on from t=0, so it is fixed at 0.
                "delay": 0.0,
                "duration": self.duration,
            }
        }
