import abc
import logging
from typing import Annotated, ClassVar

import bluepysnap as snap
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets_2.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets_2.population import (
    BiophysicalPopulationNeuronSet,
    NonVirtualPopulationNeuronSet,
    PointPopulationNeuronSet,
    PopulationBaseNeuronSet,
    PopulationNeuronSet,
    VirtualPopulationNeuronSet,
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
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN_SWEEP,
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
            if node_ids:
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

        In case of a compound expression (list expression), any new definitions
        to be combined are returned as dict.
        """
        if force_resolve_ids:
            # Resolve individual IDs per population and use in compound expression
            ids_per_npop = self.get_neuron_ids(circuit)
            expression, combined = NeuronSet.ids_to_node_set_definition(
                ids_per_npop,
                prefix=self.node_set,  # ty:ignore[invalid-argument-type]
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
            ids_dict[npop] = list(circuit.sonata_circuit.nodes[npop].ids(self.node_set))
        return ids_dict


class PredefinedPopulationBaseNeuronSet(PredefinedBaseNeuronSet, PopulationBaseNeuronSet, abc.ABC):
    """Abstract class for using an existing node set already defined in the circuit's
    node sets file resolved to a single node population.
    """

    def _resolve_ids(self, circuit: Circuit) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        self.check_node_set(circuit)
        self.check_populations_in_circuit(circuit=circuit)
        node_ids = circuit.sonata_circuit.nodes[self.population].ids(self.node_set)
        return list(node_ids)

    def _get_expression(self, circuit: Circuit) -> dict | list:
        """Returns the SONATA node set resolved in one population (w/o subsampling).

        Always resolves IDs since snap doesn't support compound
        population + node_set expressions.
        """
        node_ids = self._resolve_ids(circuit)
        return {"population": self.population, "node_id": node_ids}


class PredefinedPopulationNeuronSet(PredefinedPopulationBaseNeuronSet, PopulationNeuronSet):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected node population of any type.
    """

    title: ClassVar[str] = "Predefined Neuron Set (Any Population)"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single population of any type."
    )


class PredefinedBiophysicalPopulationNeuronSet(
    PredefinedPopulationBaseNeuronSet, BiophysicalPopulationNeuronSet
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected biophysical node population.
    """

    title: ClassVar[str] = "Predefined Neuron Set (Biophysical Population)"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single biophysical population."
    )


class PredefinedVirtualPopulationNeuronSet(
    PredefinedPopulationBaseNeuronSet, VirtualPopulationNeuronSet
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected virtual node population.
    """

    title: ClassVar[str] = "Predefined Neuron Set (Virtual Population)"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single virtual population."
    )


class PredefinedNonVirtualPopulationNeuronSet(
    PredefinedPopulationBaseNeuronSet, NonVirtualPopulationNeuronSet
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected non-virtual node population.
    """

    title: ClassVar[str] = "Predefined Neuron Set (Non-Virtual Population)"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single non-virtual population."
    )


class PredefinedPointPopulationNeuronSet(
    PredefinedPopulationBaseNeuronSet, PointPopulationNeuronSet
):
    """Use an existing node set already defined in the circuit's node sets file.

    The node set is resolved in one selected point neuron population.
    """

    title: ClassVar[str] = "Predefined Neuron Set (Point Population)"
    description: ClassVar[str] = (
        "Use neurons from a predefined node set from the SONATA circuit,"
        " resolved in a single point neuron population."
    )
