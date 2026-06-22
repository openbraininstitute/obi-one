import abc
import logging
from typing import Annotated, ClassVar

import bluepysnap as snap
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.constants import (
    BIOPHYSICAL_NEURON_SET_TITLE_SUFFIX,
    POINT_NEURON_SET_TITLE_SUFFIX,
    PREDEFINED_NEURON_SET_TITLE_PREFIX,
    VIRTUAL_NEURON_SET_TITLE_SUFFIX,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSetMixin,
    PointPopulationNeuronSetMixin,
    PopulationBaseNeuronSet,
    VirtualPopulationNeuronSetMixin,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)

L = logging.getLogger(__name__)

CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]


class PredefinedBaseNeuronSet(NeuronSet, abc.ABC):
    """Abstract base class for using an existing node set already defined in the circuit's
    node sets file.
    """

    node_set: NodeSetType = Field(
        title="Node Set",
        description="Name of the node set to use.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.NODE_SET,
        },
    )

    def check_node_set(self, circuit: Circuit) -> None:
        if self.node_set not in circuit.node_sets:
            msg = (
                f"Node set '{self.node_set}' not found in circuit '{circuit.name}'. "
                f"Available node sets: {', '.join(circuit.node_sets)}"
            )
            raise ValueError(msg)

    @staticmethod
    def get_node_set_populations(node_set: str, circuit: Circuit) -> list[str]:
        """Returns a list of all node populations a node set resolves in."""
        node_populations = []
        for npop in circuit.sonata_circuit.nodes.population_names:
            try:
                node_ids = circuit.sonata_circuit.nodes[npop].ids(node_set)
            except snap.BluepySnapError:
                # In case of an error (e.g., "No such attribute"), return empty list
                node_ids = []
            if len(node_ids) > 0:
                node_populations.append(npop)
        return node_populations


class PredefinedNeuronSet(PredefinedBaseNeuronSet):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set may span multiple populations, as defined in the circuit's
    node set definition.
    """

    title: ClassVar[str] = "Predefined Neuron Set (multi-population)"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit."
        " May span multiple node populations."
    )

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.ANY

    def _get_expression(self, circuit: Circuit) -> dict | list:
        """Returns the raw SONATA node set expression."""
        self.check_node_set(circuit)
        return [self.node_set]

    def get_populations(self, circuit: Circuit) -> list[str]:
        """Returns population names included in the neuron set."""
        self.check_node_set(circuit)
        nset_def = circuit.sonata_circuit.node_sets.content[self.node_set]

        if "population" in nset_def:
            node_populations = [nset_def["population"]]
        else:
            # Return all populations this node set resolves in
            node_populations = PredefinedBaseNeuronSet.get_node_set_populations(
                self.node_set,  # ty:ignore[invalid-argument-type]
                circuit,
            )
            if not node_populations:
                msg = (
                    f"Node set '{self.node_set}' does not resolve in any"
                    f" populations in circuit '{circuit}'!"
                )
                raise ValueError(msg)
        return node_populations

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
        if force_resolve_ids:
            # Resolve individual IDs per population and use in compound expression
            if not self.has_block_name():
                msg = "Block name must be set."
                raise ValueError(msg)
            prefix = f"__{self.__class__.__name__}__{self.block_name}"
            ids_per_npop = self.get_neuron_ids(circuit)
            expression, combined = NeuronSet.ids_to_node_set_definition(
                ids_per_npop,
                prefix=prefix,
                simplified=True,
            )
        else:
            # Symbolic expression can be preserved
            expression = self._get_expression(circuit)
            combined = {}

        return (expression, combined)

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns list of neuron IDs per population."""
        node_populations = self.get_populations(circuit)
        ids_dict = {}
        for npop in node_populations:
            try:
                node_ids = circuit.sonata_circuit.nodes[npop].ids(self.node_set).tolist()
            except snap.BluepySnapError:
                # In case of an error (e.g., "No such attribute"), return empty list
                node_ids = []
            ids_dict[npop] = node_ids

        if all(len(ids) == 0 for ids in ids_dict.values()):
            L.warning("Neuron set empty!")

        return ids_dict


class PredefinedPopulationBaseNeuronSet(PredefinedBaseNeuronSet, PopulationBaseNeuronSet, abc.ABC):
    """Abstract class for using an existing node set already defined in the circuit's
    node sets file resolved to a single node population.
    """

    def _resolve_ids(self, circuit: Circuit) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        self.check_node_set(circuit)
        self.check_populations_in_circuit(circuit)
        try:
            node_ids = circuit.sonata_circuit.nodes[self.population].ids(self.node_set)
        except snap.BluepySnapError:
            # In case of an error (e.g., "No such attribute"), return empty list
            L.warning("Neuron set empty!")
            return []
        return node_ids.tolist()

    def _get_expression(self, circuit: Circuit) -> dict | list:
        """Returns the SONATA node set resolved in one population (w/o subsampling).

        If the node set only resolves in self.population, keeps it symbolic.
        Otherwise resolves IDs since snap doesn't support compound
        population + node_set expressions.
        """
        nset_populations = PredefinedBaseNeuronSet.get_node_set_populations(
            self.node_set,  # ty:ignore[invalid-argument-type]
            circuit,
        )
        if nset_populations == [self.population]:
            # Node set only resolves in this population — keep symbolic
            self.check_populations_in_circuit(circuit)
            return [self.node_set]
        # Resolves in multiple (or none) populations — must resolve IDs for this population
        node_ids = self._resolve_ids(circuit)
        return {"population": self.population, "node_id": node_ids}


class BiophysicalPopulationPredefinedNeuronSet(
    PredefinedPopulationBaseNeuronSet, BiophysicalPopulationNeuronSetMixin
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected biophysical node population.
    """

    title: ClassVar[str] = (
        f"{PREDEFINED_NEURON_SET_TITLE_PREFIX}{BIOPHYSICAL_NEURON_SET_TITLE_SUFFIX}"
    )
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single biophysical population."
    )


class VirtualPopulationPredefinedNeuronSet(
    PredefinedPopulationBaseNeuronSet, VirtualPopulationNeuronSetMixin
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected virtual node population.
    """

    title: ClassVar[str] = f"{PREDEFINED_NEURON_SET_TITLE_PREFIX}{VIRTUAL_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single virtual population."
    )


class PointPopulationPredefinedNeuronSet(
    PredefinedPopulationBaseNeuronSet, PointPopulationNeuronSetMixin
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected point neuron population.
    """

    title: ClassVar[str] = f"{PREDEFINED_NEURON_SET_TITLE_PREFIX}{POINT_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single point neuron population."
    )
