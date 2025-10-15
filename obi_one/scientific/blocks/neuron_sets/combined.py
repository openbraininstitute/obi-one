import contextlib
import logging
from typing import Annotated

from pydantic import Field

from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")

with contextlib.suppress(ImportError):  # Try to import connalysis
    pass


class CombinedNeuronSet(NeuronSet):
    """Neuron set definition based on a combination of existing (named) node sets."""

    node_sets: (
        Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]
        | Annotated[
            list[Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]],
            Field(min_length=1),
        ]
    )

    def check_node_sets(self, circuit: Circuit, _population: str) -> None:
        for _nset in self.node_sets:
            if _nset not in circuit.node_sets:
                msg = f"Node set '{_nset}' not found in circuit '{circuit}'!"
                raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_sets(circuit, population)
        return list(self.node_sets)
