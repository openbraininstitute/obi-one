import logging
from enum import StrEnum
from typing import ClassVar

from entitysdk import Client, models
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.neuron_sets.base import NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.combined import CombinedBaseNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.unions_and_references.circuit import CircuitDiscriminator
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    CircuitExtractionNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit components"


class CircuitExtractionScanConfig(InfoScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    name: ClassVar[str] = "Circuit Extraction"
    description: ClassVar[str] = (
        "Extracts a sub-circuit from a SONATA circuit as defined by a neuron set. The output"
        " circuit will contain all morphologies, hoc files, and mod files that are required"
        " to simulate the extracted circuit."
    )

    default_node_set_name: ClassVar[str] = "Default: All Biophysical Neurons"
    default_point_node_set_name: ClassVar[str] = "Default: All Point Neurons"
    default_neuron_set_type: ClassVar[type[AllBiophysicalNeurons]] = AllBiophysicalNeurons
    default_point_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    @property
    def default_neuron_set_reference(
        self,
    ) -> BiophysicalNeuronSetReference:
        """The default neuron set reference for the simulation."""
        default_neuron_set_block_reference = BiophysicalNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )

        default_neuron_set_block_reference.block = self.default_neuron_set_type()
        default_neuron_set_block_reference.block.set_block_name(self.default_node_set_name)

        return default_neuron_set_block_reference

    @property
    def default_point_neuron_set_reference(
        self,
    ) -> PointNeuronSetReference:
        """The default point neuron set reference for the simulation."""
        ref = PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_point_node_set_name
        )
        ref.block = self.default_point_neuron_set_type()
        ref.block.set_block_name(self.default_point_node_set_name)
        return ref

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            BiophysicalNeuronSetReference.__name__: default_node_set_name,
            PointNeuronSetReference.__name__: default_point_node_set_name,
        },
    }

    def input_entities(self, db_client: Client) -> list[models.Entity]:
        input_entities = []
        if isinstance(self.initialize.circuit, CircuitFromID):
            input_entities.extend([self.initialize.circuit.entity(db_client=db_client)])
        elif isinstance(self.initialize.circuit, list):
            for circuit in self.initialize.circuit:
                if isinstance(circuit, CircuitFromID):
                    input_entities.extend([circuit.entity(db_client=db_client)])
        return input_entities

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            },
        )
        neuron_set: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(  # ty:ignore[no-matching-overload]
            default=None,
            title="Neuron set",
            description="Set of neurons to be extracted from the parent circuit, including their"
            " connectivity.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
            },
        )
        do_virtual: bool = Field(
            default=True,
            title="Include virtual populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
            },
        )
        create_external: bool = Field(
            default=True,
            title="Create external population",
            description="Convert (non-virtual) neurons which are outside of the specified neuron"
            " set, but which target the cells contained therein, into a new external population"
            " of virtual neurons (together with their connectivity onto the specified neuron set).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
            },
        )

    info: Info = Field(
        title="Info",
        description="Information about the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    neuron_sets: dict[str, CircuitExtractionNeuronSetUnion] = Field(  # ty:ignore[no-matching-overload]
        title="Neuron sets",
        default_factory=dict,
        description="Neuron sets for the extraction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def ensure_extraction_target_neuron_set(self) -> None:
        """Ensure a neuron set reference exists for initialize.neuron_set.

        If neuron_set is None, sets it to the default biophysical neuron set
        reference and ensures the corresponding block exists in neuron_sets.
        """
        if self.initialize.neuron_set is None:
            L.info("initialize.neuron_set is None — setting default neuron set.")
            self.initialize.neuron_set = self._default_neuron_set_ref()

    def _default_neuron_set_ref(self) -> BiophysicalNeuronSetReference:
        """Returns the reference for the default neuron set, adding it to neuron_sets if needed."""
        ref = self.default_neuron_set_reference
        if ref.block_name in self.neuron_sets and not isinstance(
            self.neuron_sets[ref.block_name], self.default_neuron_set_type
        ):
            msg = (
                f"Default neuron set name '{ref.block_name}' already exists in "
                f"neuron_sets but is not an {self.default_neuron_set_type.__name__} set!"
            )
            raise OBIONEError(msg)
        if ref.block_name not in self.neuron_sets:
            self.neuron_sets[ref.block_name] = ref.block  # ty:ignore[invalid-assignment]
        return ref

    def _default_point_neuron_set_ref(self) -> PointNeuronSetReference:
        """Returns the reference for the default point neuron set, adding it if needed."""
        ref = self.default_point_neuron_set_reference
        if ref.block_name in self.neuron_sets and not isinstance(
            self.neuron_sets[ref.block_name], self.default_point_neuron_set_type
        ):
            msg = (
                f"Default point neuron set name '{ref.block_name}' already exists in "
                f"neuron_sets but is not an {self.default_point_neuron_set_type.__name__} set!"
            )
            raise OBIONEError(msg)
        if ref.block_name not in self.neuron_sets:
            self.neuron_sets[ref.block_name] = ref.block  # ty:ignore[invalid-assignment]
        return ref

    def ensure_combined_neuron_sets_have_references(self) -> None:
        """Ensure combined neuron sets in the dictionary have their references filled."""
        for neuron_set in list(self.neuron_sets.values()):
            if isinstance(neuron_set, CombinedBaseNeuronSet):
                self._ensure_combined_neuron_set_has_references(neuron_set)

    def _ensure_combined_neuron_set_has_references(self, neuron_set: CombinedBaseNeuronSet) -> None:
        """Ensure a combined neuron set's base and combined_with references are filled."""
        default_ref = self._default_neuron_set_ref_for_population_type(
            neuron_set.get_neuron_set_population_type()
        )

        if neuron_set.base_neuron_set is None:
            neuron_set.base_neuron_set = default_ref

        updated_entries = []
        for ref, op in neuron_set.combined_with:
            if ref is None:
                updated_entries.append((default_ref, op))
            else:
                updated_entries.append((ref, op))
        neuron_set.combined_with = tuple(updated_entries)

    def _default_neuron_set_ref_for_population_type(
        self, population_type: NeuronSetPopulationType
    ) -> NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION:
        """Returns the appropriate default neuron set reference for the given population type."""
        if population_type == NeuronSetPopulationType.POINT:
            return self._default_point_neuron_set_ref()
        return self._default_neuron_set_ref()


class CircuitExtractionSingleConfig(CircuitExtractionScanConfig, SingleConfigMixin):
    """Extracts a sub-circuit of a SONATA circuit as defined by a node set.

    The output circuit will contain all morphologies, hoc files, and mod files
    that are required to simulate the extracted circuit.
    """
