import abc
import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    PopulationBaseNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")


class IDPopulationBaseNeuronSet(PopulationBaseNeuronSet, abc.ABC):
    """Abstract base class for neuron sets provided by a list of neuron IDs."""

    neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)] = Field(
        title="Neuron IDs",
        description="List of neuron IDs to include in the neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_IDS,
        },
    )

    def check_neuron_ids(self, circuit: Circuit) -> None:
        self.check_populations_in_circuit(circuit=circuit)
        popul_ids = circuit.sonata_circuit.nodes[self.population].ids()
        if not all(nid in popul_ids for nid in self.neuron_ids.elements):  # ty:ignore[unresolved-attribute]
            msg = (
                f"Neuron ID(s) not found in population '{self.population}' "
                f"of circuit '{circuit.name}'. "
                f"Available neuron ids: {', '.join(str(nid) for nid in popul_ids)}"
            )
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_neuron_ids(circuit)
        return {"population": self.population, "node_id": list(self.neuron_ids.elements)}  # ty:ignore[unresolved-attribute]


class BiophysicalPopulationIDNeuronSet(IDPopulationBaseNeuronSet, BiophysicalPopulationNeuronSet):
    """Neuron set definition by providing a list of neuron IDs.

    Resolved in one selected biophysical node population.
    """

    title: ClassVar[str] = "BY ID (Biophysical)"
    description: ClassVar[str] = (
        "Use neurons by providing a list of IDs, resolved in a single biophysical population."
    )


class VirtualPopulationIDNeuronSet(IDPopulationBaseNeuronSet, VirtualPopulationNeuronSet):
    """Neuron set definition by providing a list of neuron IDs.

    Resolved in one selected virtual node population.
    """

    title: ClassVar[str] = "Sample IDs (Virtual)"
    description: ClassVar[str] = (
        "Use neurons by providing a list of IDs, resolved in a single virtual population."
    )


class PointPopulationIDNeuronSet(IDPopulationBaseNeuronSet, PointPopulationNeuronSet):
    """Neuron set definition by providing a list of neuron IDs.

    Resolved in one selected point neuron population.
    """

    title: ClassVar[str] = "Sample IDs (Point)"
    description: ClassVar[str] = (
        "Use neurons by providing a list of IDs, resolved in a single point neuron population."
    )
