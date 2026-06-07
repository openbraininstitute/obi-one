import logging

import bluepysnap as snap
import h5py
import numpy as np
import pandas as pd
from connectome_manipulator.model_building import model_types
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
)
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


class AllPairsSynapticModelAssigner(SynapseModelAssigner):

    def validate(self, circuit: Circuit) -> None:
        pass
    
    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        return ep.ids()
