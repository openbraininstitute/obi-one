import abc
import numpy as np
from obi.modeling.core.block import Block
from obi.modeling.circuit.circuit import Circuit

class NeuronSet(Block, abc.ABC):
    """
    Abstract base class representing a neuron set of a node populations.
    """
    circuit: Circuit
    population: str
    random_sample: None | int | float = None
    random_seed: int = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        assert self.population in self.circuit.node_population_names, f"ERROR: Node population '{self.population}' not found!"

        if self.random_sample is not None:
            if isinstance(self.random_sample, int):
                assert self.random_sample >=0, "ERROR: Random sample number must not be negative!"
            elif isinstance(self.random_sample, float):
                assert 0.0 <= self.random_sample <= 1.0, "ERROR: Random sample fraction must be between 0.0 and 1.0!"

    @abc.abstractmethod
    def _resolve_ids(self):
        """Returns the full list of neuron IDs (w/o subsampling)."""
        pass

    @property
    def ids(self):
        """Returns list of neuron IDs."""
        ids = np.array(self._resolve_ids())
        if self.random_sample is not None:
            np.random.seed(self.random_seed)

            if isinstance(self.random_sample, int):
                num_sample = np.minimum(self.random_sample, len(ids))
            elif isinstance(self.random_sample, float):
                num_sample = np.round(self.random_sample * len(ids)).astype(int)

            ids = ids[np.random.permutation([True] * num_sample + [False] * (len(ids) - num_sample))]
        return ids

    @property
    def size(self):
        """Returns the size (#neurons) of the neuron set."""
        return len(self.ids)


class IDNeuronSet(NeuronSet):
    """
    Neuron set definition by providing a list of neuron IDs.
    """
    neuron_ids: list[int]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        _ids = self.circuit.sonata_circuit.nodes[self.population].ids(self.neuron_ids)  # Try accessing IDs

    def _resolve_ids(self):
        """Returns the full list of neuron IDs (w/o subsampling)."""
        return self.neuron_ids


class PropertyNeuronSet(NeuronSet):
    """
    Neuron set definition based on neuron properties.
    """
    property_specs: dict

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        assert all(_k in self.circuit.sonata_circuit.nodes[self.population].property_names for _k in self.property_specs.keys()), "ERROR: Invalid neuron properties!"

    def _resolve_ids(self):
        """Returns the full list of neuron IDs (w/o subsampling)."""
        return self.circuit.sonata_circuit.nodes[self.population].ids(self.property_specs)
