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

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.constants import (
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag


class Brian2DirectPoissonStimulus(Block):
    """Independent Poisson drive injected directly into the soma.

    Each neuron receives its own Poisson Input directly into the soma
    firing. Each spike adds a weight to the membrane potential.
    """

    title: ClassVar[str] = "Direct Poisson Input"

    neuron_set: POINT_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Neurons that receive the Poisson drive.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.REFERENCE_TAG: ReferenceTag.STIMULUS_TARGET,
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
            "Amplitude of each injection, in millivolts. The default value is taken "
            "from the original Shui et al. (2024) LIF FlyWire model simulations."
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
        description=(
            "Informational only; Brian2 PoissonInput is always-on for the whole "
            "simulation. Recorded in the SONATA entry for forward compatibility."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def config(self) -> dict:
        """Return the SONATA inputs entry for this block.

        The biophysical check that :class:`ContinuousStimulusWithoutTimestamps`
        applies is deliberately skipped: this stimulus injects directly into
        ``v`` (or any target variable) and is valid for point-neuron and
        biophysical populations alike.
        """
        return self._generate_config()

    def _generate_config(self) -> dict:
        node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set)

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
