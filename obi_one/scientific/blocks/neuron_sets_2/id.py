"""IDNeuronSet(PopulationNeuronSet).

- As before, selected IDs within a given node population
"""

import abc
import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets_2.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    PopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")


class IDNeuronSet(PopulationNeuronSet, abc.ABC):
    """Neuron set definition by providing a list of neuron IDs."""

    neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)] = Field(
        title="ID Neuronset",
        description="List of neuron IDs to include in the neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_IDS,
        },
    )

    def check_neuron_ids(self, circuit: Circuit) -> None:
        popul_ids = circuit.sonata_circuit.nodes[self.population].ids()
        if not all(_nid in popul_ids for _nid in self.neuron_ids.elements):
            msg = (
                f"Neuron ID(s) not found in population '{self.population}' "
                f"of circuit '{circuit.name}'. "
                f"Available neuron ids: {', '.join(str(nid) for nid in popul_ids)}"
            )
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_neuron_ids(circuit)
        return {"population": self.population, "node_id": list(self.neuron_ids.elements)}


class BiophysicalIDNeuronSet(IDNeuronSet, BiophysicalPopulationNeuronSet):
    """Only biophysical neuron node populations are selectable."""

    title: ClassVar[str] = "Sample IDs (Biophysical)"


class VirtualIDNeuronSet(IDNeuronSet, VirtualPopulationNeuronSet):
    """Only virtual neuron node populations are selectable."""

    title: ClassVar[str] = "Sample IDs (Virtual)"


class PointIDNeuronSet(IDNeuronSet, PointPopulationNeuronSet):
    """Only point neuron node populations are selectable."""

    title: ClassVar[str] = "Sample IDs (Point)"
