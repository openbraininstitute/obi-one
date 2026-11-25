"""Configuration for generating NEST-compatible SONATA simulation configs.

Mirrors ``Brian2CircuitSimulationScanConfig`` but restricts blocks to those supported by the NEST
runner (``obi_one/scientific/library/simulation/nest/simulate_nest.py``) on circuits in the
SONATA-extension NEST format.
"""

from typing import ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.generate_simulations.config.base import (
    DEFAULT_DISTRIBUTION_NAME,
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.nest.nest_base import (
    NestSimulationScanConfig,
)
from obi_one.scientific.unions_and_references.circuit import CircuitDiscriminator
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    POINT_AND_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    NestSimulationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.manipulations import (
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions_and_references.stimuli import (
    NestCircuitStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions_and_references.timestamps import TimestampsReference


class NestCircuitSimulationScanConfig(NestSimulationScanConfig):
    """Configuration for generating NEST-targeted SONATA simulation configs.

    Only exposes stimulus, recording and neuron set types that the NEST runner supports. The
    generated ``simulation_config.json`` has ``target_simulator: "NEST"``.
    """

    name: ClassVar[str] = "NEST Simulation Campaign"
    description: ClassVar[str] = "NEST-targeted SONATA simulation campaign"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            PointNeuronSetReference.__name__: NestSimulationScanConfig.default_node_set_name,
            VirtualNeuronSetReference.__name__: (
                NestSimulationScanConfig.default_virtual_node_set_name
            ),
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
            AllDistributionsReference.__name__: DEFAULT_DISTRIBUTION_NAME,
        },
    }

    class Initialize(NestSimulationScanConfig.Initialize):
        """Initialization parameters for a NEST circuit simulation."""

        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )
        node_set: POINT_NEURON_SETS_REFERENCE_UNION | None = Field(  # ty:ignore[no-matching-overload]
            default=None,
            title="Neuron set",
            description="Neuron set to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 99,
                SchemaKey.UI_HIDDEN: True,
            },
        )
        # NEST models start at their own resting potential; the runner ignores `conditions`.
        v_init: float | list[float] = Field(
            default=-80.0,
            title="Initial voltage",
            description="Initial membrane potential in millivolts (mV). Not used by NEST.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLIVOLTS,
                SchemaKey.UI_HIDDEN: True,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    stimuli: dict[str, NestCircuitStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="NEST-compatible stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [StimulusReference.__name__],
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    neuron_sets: dict[str, NestSimulationNeuronSetUnion] = Field(  # ty:ignore[no-matching-overload]
        title="Neuron sets",
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: POINT_AND_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    distributions: dict[str, AllDistributionsUnion] = Field(
        default_factory=dict,
        title="Distributions",
        description="Distributions used by stimuli (e.g. inter-spike interval distributions).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Distribution",
            SchemaKey.GROUP: BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        title="Synaptic manipulations",
        default_factory=dict,
        description="Synaptic manipulations for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticManipulationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Manipulation",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class NestCircuitSimulationSingleConfig(
    NestCircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
