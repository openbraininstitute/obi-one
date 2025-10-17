import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets.base import AbstractNeuronSet
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")


class IDNeuronSet(AbstractNeuronSet):
    """Neuron set definition by providing a list of neuron IDs."""

    title: ClassVar[str] = "ID Neuron Set"

    neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)]

    def check_neuron_ids(self, circuit: Circuit, population: str) -> None:
        popul_ids = circuit.sonata_circuit.nodes[population].ids()
        if not all(_nid in popul_ids for _nid in self.neuron_ids.elements):
            msg = f"Neuron ID(s) not found in population '{population}' of circuit '{circuit}'!"
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        population = self._population(population)
        self.check_neuron_ids(circuit, population)
        return {"population": population, "node_id": list(self.neuron_ids.elements)}
