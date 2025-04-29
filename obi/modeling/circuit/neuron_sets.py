import abc
import bluepysnap as snap
import json
import numpy as np
import os
from obi.modeling.core.block import Block
from obi.modeling.circuit.circuit import Circuit
from pydantic import Field, model_validator
from typing import Annotated
from typing_extensions import Self


class NeuronSet(Block, abc.ABC):
    """
    Base class representing a neuron set of a single SONATA node populations.
    """
    name: Annotated[str, Field(min_length=1)]
    circuit: Circuit
    population: Annotated[str, Field(min_length=1)]
    random_sample: None | int | float = None
    random_seed: int = 0

    @model_validator(mode='after')
    def check_name(self) -> Self:
        assert self.name not in self.circuit.node_sets, f"Neuron set '{self.name}' already exists in the circuit's node sets!"
        return self

    @model_validator(mode='after')
    def check_population(self) -> Self:
        assert self.population in self.circuit.node_population_names, f"Node population '{self.population}' not found!"
        return self

    @model_validator(mode='after')
    def check_random_sample(self) -> Self:
        if self.random_sample is not None:
            if isinstance(self.random_sample, int):
                assert self.random_sample >= 0, "Random sample number must not be negative!"
            elif isinstance(self.random_sample, float):
                assert 0.0 <= self.random_sample <= 1.0, "Random sample fraction must be between 0.0 and 1.0!"
        return self

    @abc.abstractmethod
    def _get_expression(self):
        """Returns the SONATA node set expression (w/o subsampling)."""
        pass

    @staticmethod
    def add_node_set_to_circuit(sonata_circuit, node_set_dict, overwrite_if_exists=False):
        """Adds the node set definition to a SONATA circuit object to make it accessible (in-place)."""
        existing_node_sets = sonata_circuit.node_sets.content
        if not overwrite_if_exists:
            for _k in node_set_dict.keys():
                assert _k not in existing_node_sets, f"Node set '{_k}' already exists!"
        existing_node_sets.update(node_set_dict)
        sonata_circuit.node_sets = snap.circuit.NodeSets.from_dict(existing_node_sets)

    @staticmethod
    def write_circuit_node_set_file(sonata_circuit, output_path, file_name=None, overwrite_if_exists=False):
        """Writes a new node set file of a given SONATA circuit object."""
        if file_name is None:
            # Use circuit's node set file name by default
            file_name = os.path.split(sonata_circuit.config["node_sets_file"])[1]
        else:
            assert isinstance(file_name, str) and len(file_name) > 0, "File name must be a non-empty string! Can be omitted to use default file name."
            fname, fext = os.path.splitext(file_name)
            assert len(fname) > 0 and fext.lower() == ".json", "File name must be non-empty and of type .json!"
        output_file = os.path.join(output_path, file_name)

        if not overwrite_if_exists:
            assert not os.path.exists(output_file), f"Output file '{output_file}' already exists! Delete file or choose to overwrite."

        with open(output_file, "w") as f:
            json.dump(sonata_circuit.node_sets.content, f)

    def _resolve_ids(self):
        """Returns the full list of neuron IDs (w/o subsampling)."""
        c = self.circuit.sonata_circuit
        self.add_node_set_to_circuit(c, {self.name: self._get_expression()})
        return c.nodes[self.population].ids(self.name)

    def get_ids(self, with_population=False):
        """Returns list of neuron IDs (with subsampling, if specified)."""
        ids = np.array(self._resolve_ids())
        if self.random_sample is not None:
            np.random.seed(self.random_seed)

            if isinstance(self.random_sample, int):
                num_sample = np.minimum(self.random_sample, len(ids))
            elif isinstance(self.random_sample, float):
                num_sample = np.round(self.random_sample * len(ids)).astype(int)

            ids = ids[np.random.permutation([True] * num_sample + [False] * (len(ids) - num_sample))]

        if with_population:
            return {self.population: ids}
        else:
            return ids

    @property
    def size(self):
        """Returns the size (#neurons) of the neuron set."""
        return len(self.get_ids())

    def get_node_set_dict(self, force_resolve_ids=False):
        """Returns the SONATA node set definition as dict, optionally forcing to resolve individual IDs."""
        if self.random_sample is None and not force_resolve_ids:
            # Symbolic expression can be preserved
            expression = self._get_expression()
        else:
            # Individual IDs need to be resolved
            expression = {"population": self.population, "node_id": self.get_ids().tolist()}

        return {self.name: expression}

    def write_node_set_file(self, output_path, file_name=None, overwrite_if_exists=False, append_if_exists=False, force_resolve_ids=False):
        """Writes a new node set file of a circuit."""
        if file_name is None:
            # Use circuit's node set file name by default
            file_name = os.path.split(self.circuit.sonata_circuit.config["node_sets_file"])[1]
        else:
            assert isinstance(file_name, str) and len(file_name) > 0, "File name must be a non-empty string! Can be omitted to use default file name."
            fname, fext = os.path.splitext(file_name)
            assert len(fname) > 0 and fext.lower() == ".json", "File name must be non-empty and of type .json!"
        output_file = os.path.join(output_path, file_name)

        assert not (overwrite_if_exists and append_if_exists), "Append and overwrite options are mutually exclusive!"

        if not os.path.exists(output_file) or overwrite_if_exists:
            # Create new node sets file from circuit object, overwrite if existing
            node_sets = self.circuit.sonata_circuit.node_sets.content
            node_sets.update(self.get_node_set_dict(force_resolve_ids=force_resolve_ids))

        elif os.path.exists(output_file) and append_if_exists:
            # Append to existing node sets file
            with open(output_file, "r") as f:
                node_sets = json.load(f)
                assert self.name not in node_sets, f"Appending not possible, node set '{self.name}' already exists!"
                node_sets.update(self.get_node_set_dict(force_resolve_ids=force_resolve_ids))

        else:  # File existing but no option chosen
            assert False, f"Output file '{output_file}' already exists! Delete file or choose to append or overwrite."
                
        with open(output_file, "w") as f:
            json.dump(node_sets, f)

        return output_file


class BasicNeuronSet(NeuronSet):
    """
    Basic neuron set definition based on a combination of existing (named) node sets.
    """
    node_sets: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]

    @model_validator(mode='after')
    def check_node_sets(self) -> Self:
        for _nset in self.node_sets:
            assert _nset in self.circuit.node_sets, f"Node set '{_nset}' not found!"
        return self

    def _get_expression(self):
        """Returns the SONATA node set expression (w/o subsampling)."""
        return self.node_sets


class IDNeuronSet(NeuronSet):
    """
    Neuron set definition by providing a list of neuron IDs.
    """
    neuron_ids: Annotated[list[int], Field(min_length=1)]

    @model_validator(mode='after')
    def check_neuron_ids(self) -> Self:
        popul_ids = self.circuit.sonata_circuit.nodes[self.population].ids()
        assert all(_nid in popul_ids for _nid in self.neuron_ids), f"Neuron ID(s) not in population '{self.population}'!"
        return self

    def _get_expression(self):
        """Returns the SONATA node set expression (w/o subsampling)."""
        return {"population": self.population, "node_id": self.neuron_ids}


class PropertyNeuronSet(NeuronSet):
    """
    Neuron set definition based on neuron properties, optionally combined with (named) node sets.
    """
    property_specs: Annotated[dict, Field(min_length=1)]
    node_sets: list[Annotated[str, Field(min_length=1)]] = []

    @model_validator(mode='after')
    def check_properties(self) -> Self:
        prop_names = self.circuit.sonata_circuit.nodes[self.population].property_names
        assert all(_prop in prop_names for _prop in self.property_specs.keys()), f"Invalid neuron properties! Available properties: {prop_names}"
        return self

    @model_validator(mode='after')
    def check_node_sets(self) -> Self:
        for _nset in self.node_sets:
            assert _nset in self.circuit.node_sets, f"Node set '{_nset}' not found!"
        return self

    def _get_expression(self):
        """Returns the SONATA node set expression (w/o subsampling)."""
        if len(self.node_sets) == 0:
            # Symbolic expression can be preserved
            expression = self.property_specs
        else:
            # Individual IDs need to be resolved
            c = self.circuit.sonata_circuit
            node_ids = np.array([]).astype(int)
            for _nset in self.node_sets:
                node_ids = np.union1d(node_ids, c.nodes[self.population].ids(_nset))
            node_ids = np.intersect1d(node_ids, c.nodes[self.population].ids(self.property_specs))

            expression = {"population": self.population, "node_id": node_ids.tolist()}

        return expression
