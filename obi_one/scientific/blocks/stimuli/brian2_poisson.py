"""Brian2-specific direct-injection Poisson stimulus block.

Drives each neuron in ``neuron_set`` with its own independent Poisson spike
train, kicking the target membrane potential directly.

The runner builds one ``brian2.PoissonInput`` per contiguous range of node IDs
in the target, each with ``N=1`` so that every neuron it covers still gets an
independent train. How many objects that is depends on how the target's IDs
happen to fall: ``[0, 1, 2, 3, 4]`` is a single one, ``[0, 2, 4, 6]`` is four.

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
from obi_one.scientific.library.constants import (
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions_and_references.timestamps import TimestampsReference


class Brian2DirectPoissonStimulus(Block):
    """Independent Poisson drive injected directly into the soma.

    Each target neuron receives its own spike train, and every spike steps that
    neuron's membrane potential by the weight.
    """

    title: ClassVar[str] = "Direct Poisson Input"

    neuron_set: POINT_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Neurons that receive the Poisson drive.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    frequency: (
        Annotated[NonNegativeFloat, Field(le=150.0)]
        | list[Annotated[NonNegativeFloat, Field(le=150.0)]]
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
        default=68.75,
        title="Weight",
        description=(
            "How much each spike adds to the membrane potential, in millivolts (mV). "
            "The default is the value used by Shui et al. (2024)."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )

    duration: (
        Annotated[NonNegativeFloat, Field(le=MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        # Recorded in the generated config for forward compatibility, but the runner's
        # PoissonInput is always-on, so the value has no effect on the simulation yet.
        description=(
            "How long the drive lasts, in milliseconds (ms). It currently runs for the "
            "whole simulation whatever this is set to."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    _default_node_set: str = PrivateAttr(default="All")

    def config(
        self,
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
