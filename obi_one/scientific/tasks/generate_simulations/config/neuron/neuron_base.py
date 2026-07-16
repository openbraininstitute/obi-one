import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.library.constants import (
    SIMULATION_TIMESTEP_MILLISECONDS,
    SONATA,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
    BlockGroup,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
    MorphologyLocationUnion,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions_and_references.recordings import (
    RecordingReference,
    RecordingUnion,
)
from obi_one.scientific.unions_and_references.timestamps import (
    TimestampsReference,
    TimestampsUnion,
)


class NeuronSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for neuron-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.NEURON
    _spike_location: ClassVar[str] = SONATA.SPIKE_LOCATION_SOMA
    _timestep: ClassVar[PositiveFloat] = SIMULATION_TIMESTEP_MILLISECONDS
    default_node_set_name: ClassVar[str] = "Default: All Biophysical Neurons"
    default_virtual_node_set_name: ClassVar[str] = "Default: All Virtual Neurons"
    default_point_node_set_name: ClassVar[str] = "Default: All Point Neurons"
    default_neuron_set_type: ClassVar[type[AllBiophysicalNeurons]] = AllBiophysicalNeurons
    default_virtual_neuron_set_type: ClassVar[type[AllVirtualNeurons]] = AllVirtualNeurons
    default_point_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    @property
    def default_neuron_set_reference(
        self,
    ) -> BiophysicalNeuronSetReference:
        """Returns the default neuron set reference for the simulation."""
        default_neuron_set_block_reference = BiophysicalNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )

        default_neuron_set_block_reference.block = self.default_neuron_set_type()
        default_neuron_set_block_reference.block.set_block_name(self.default_node_set_name)

        return default_neuron_set_block_reference

    @property
    def default_virtual_neuron_set_reference(
        self,
    ) -> VirtualNeuronSetReference:
        """Returns the default virtual neuron set reference for the simulation."""
        ref = VirtualNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_virtual_node_set_name
        )
        ref.block = self.default_virtual_neuron_set_type()
        ref.block.set_block_name(self.default_virtual_node_set_name)
        return ref

    @property
    def default_point_neuron_set_reference(
        self,
    ) -> PointNeuronSetReference:
        """Returns the default point neuron set reference for the simulation."""
        ref = PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_point_node_set_name
        )
        ref.block = self.default_point_neuron_set_type()
        ref.block.set_block_name(self.default_point_node_set_name)
        return ref

    recordings: dict[str, RecordingUnion] = Field(
        default_factory=dict,
        description="Recordings for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [RecordingReference.__name__],
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    morphology_locations: dict[str, MorphologyLocationUnion] = Field(
        default_factory=dict,
        title="Morphology Locations",
        description="Rules to generate locations on morphologies.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Morphology Locations",
            SchemaKey.GROUP: BlockGroup.TARGETING_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [TimestampsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Timestamps",
            SchemaKey.GROUP: BlockGroup.EVENTS_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    class Initialize(BaseSimulationScanConfig.Initialize):
        extracellular_calcium_concentration: NonNegativeFloat | list[NonNegativeFloat] = Field(
            default=1.1,
            title="Extracellular Calcium Concentration",
            description=(
                "Extracellular calcium concentration around the synapse in millimoles (mM). "
                "Increasing this value increases the probability of synaptic vesicle release, "
                "which in turn increases the level of network activity. In vivo values are "
                "estimated to be ~0.9-1.2mM, whilst in vitro values are on the order of 2mM."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLIMOLAR,
            },
        )

    def base_sonata_config(self, sonata_config: dict | None = None) -> dict:
        """Returns the base SONATA configuration for the simulation campaign."""
        sonata_config = super().base_sonata_config(sonata_config)

        sonata_config["conditions"]["spike_location"] = self._spike_location

        return sonata_config
