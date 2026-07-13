import logging

import numpy as np

from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


class AllPairsSynapticModelAssigner(SynapseModelAssigner):
    """Assign a synaptic model to all synapses in the edge population."""

    def validate_for_circuit(self, circuit: Circuit) -> None:
        pass

    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        return ep.ids()
