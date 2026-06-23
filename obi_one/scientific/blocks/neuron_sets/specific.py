import abc
import logging
from typing import ClassVar

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.constants import (
    ALL_NEURON_SET_TITLE_PREFIX,
    ALL_POPULATION_TYPES_NEURON_SET_TITLE_SUFFIX,
    BIOPHYSICAL_NEURON_SET_TITLE_SUFFIX,
    POINT_NEURON_SET_TITLE_SUFFIX,
    VIRTUAL_NEURON_SET_TITLE_SUFFIX,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)

L = logging.getLogger(__name__)


class AllNeuronsBase(NeuronSet, abc.ABC):
    """Abstract base class for neuron sets selecting all neurons of a given type."""

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns all neuron IDs per population."""
        ids_dict = {}
        for npop in self.get_populations(circuit):
            ids_dict[npop] = circuit.sonata_circuit.nodes[npop].ids().tolist()
        return ids_dict

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        Returns a tuple of (expression, combined) where:

        - expression (dict): A single SONATA node set expression. Examples:
            - Symbolic by population: {"population": "pop_name"}
            - Symbolic by properties: {"layer": "6", "synapse_class": "EXC"}
            - Resolved IDs: {"population": "pop_name", "node_id": [1, 2, 3]}

        - expression (list): A compound expression referencing multiple named node sets.
            Example: ["__ClassName__blockname__0__", "__ClassName__blockname__1__"]
            Each name must exist as a key in the combined dict.
            Also used for symbolic references to existing node sets: ["Layer6"]

        - combined (dict): Additional node set definitions needed by a compound expression.
            Example: {"__ClassName__blockname__0__": {"population": "A", "node_id": [...]},
                      "__ClassName__blockname__1__": {"population": "B", "node_id": [...]}}
            Empty ({}) when expression is a single dict.

        Args:
            circuit: The circuit to resolve the node set in.
            force_resolve_ids: If True, always resolve to explicit neuron IDs
                instead of preserving symbolic expressions.
        """
        if not self.has_block_name():
            msg = "Block name must be set."
            raise ValueError(msg)
        if force_resolve_ids:
            ids_per_npop = self.get_neuron_ids(circuit)
            prefix = f"__{self.__class__.__name__}__{self.block_name}"
            return NeuronSet.ids_to_node_set_definition(
                ids_per_npop, prefix=prefix, simplified=True
            )
        # Symbolic: list all population node sets
        populations = self.get_populations(circuit)
        if len(populations) == 1:
            return {"population": populations[0]}, {}
        expression = []
        combined = {}
        for idx, npop in enumerate(populations):
            key = f"__{self.__class__.__name__}__{self.block_name}__{idx}__"
            combined[key] = {"population": npop}
            expression.append(key)
        return expression, combined


class AllNeurons(AllNeuronsBase):
    """All neurons across all populations."""

    title: ClassVar[str] = (
        f"{ALL_NEURON_SET_TITLE_PREFIX}{ALL_POPULATION_TYPES_NEURON_SET_TITLE_SUFFIX}"
    )
    description: ClassVar[str] = "All neurons from all node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.ANY

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all population names in the circuit."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=True,
            incl_point=True,
            incl_virtual=True,
        )


class AllBiophysicalNeurons(AllNeuronsBase):
    """All biophysical neurons across all biophysical populations."""

    title: ClassVar[str] = f"{ALL_NEURON_SET_TITLE_PREFIX}{BIOPHYSICAL_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = "All neurons from all biophysical node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_BIOPHYSICAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no biophysical populations.",
        },
    }

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all biophysical population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=True,
            incl_point=False,
            incl_virtual=False,
        )


class AllPointNeurons(AllNeuronsBase):
    """All point neurons across all point neuron populations."""

    title: ClassVar[str] = f"{ALL_NEURON_SET_TITLE_PREFIX}{POINT_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = "All neurons from all point neuron populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.POINT

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_POINT_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no point neuron populations.",
        },
    }

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all point neuron population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=False,
            incl_point=True,
            incl_virtual=False,
        )


class AllVirtualNeurons(AllNeuronsBase):
    """All virtual neurons across all virtual populations."""

    title: ClassVar[str] = f"{ALL_NEURON_SET_TITLE_PREFIX}{VIRTUAL_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = "All neurons from all virtual node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_VIRTUAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no virtual populations.",
        },
    }

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all virtual population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=False,
            incl_point=False,
            incl_virtual=True,
        )


class AllNonVirtualNeurons(AllNeuronsBase):
    """All non-virtual neurons (biophysical + point) across all populations."""

    title: ClassVar[str] = "All Non-Virtual Neurons"
    description: ClassVar[str] = "All neurons from all non-virtual node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.NONVIRTUAL
    )

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all non-virtual population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=True,
            incl_point=True,
            incl_virtual=False,
        )
