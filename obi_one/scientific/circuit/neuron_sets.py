import abc
import json
import os
from typing import Annotated, Self

import bluepysnap as snap
import numpy as np
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.list import NamedTuple


class NeuronSet(Block, abc.ABC):
    """Base class representing a neuron set which can be turned into a SONATA node set by either
    adding it to an existing SONATA circuit object (add_node_set_to_circuit) or writing it to a
    SONATA node set .json file (write_circuit_node_set_file).
    Whenever such a neuron set is used in a SimulationsForm, it must be added to its neuron_sets
    dictionary with the key being the name of the SONATA node set which will internally be set
    in simulation_level_name upon initialization of the SimulationsForm.
    """

    simulation_level_name: (
        None | Annotated[str, Field(min_length=1, description="Name within a simulation.")]
    ) = None
    random_sample: None | int | float | list[None | int | float] = None
    random_seed: int | list[int] = 0

    @model_validator(mode="after")
    def check_random_sample(self) -> Self:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.random_sample, list):
            if self.random_sample is not None:
                if isinstance(self.random_sample, int):
                    assert self.random_sample >= 0, "Random sample number must not be negative!"
                elif isinstance(self.random_sample, float):
                    assert 0.0 <= self.random_sample <= 1.0, (
                        "Random sample fraction must be between 0.0 and 1.0!"
                    )
        return self

    def check_simulation_init(self):
        assert self.simulation_level_name is not None, (
            f"'{self.__class__.__name__}' initialization within a simulation required!"
        )

    @abc.abstractmethod
    def _get_expression(self, circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""

    @property
    def name(self):
        self.check_simulation_init()
        return self.simulation_level_name

    @staticmethod
    def check_population(circuit, population):
        assert population in circuit.get_node_population_names(), (
            f"Node population '{population}' not found in circuit '{circuit}'!"
        )

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
    def write_circuit_node_set_file(
        sonata_circuit, output_path, file_name=None, overwrite_if_exists=False
    ):
        """Writes a new node set file of a given SONATA circuit object."""
        if file_name is None:
            # Use circuit's node set file name by default
            file_name = os.path.split(sonata_circuit.config["node_sets_file"])[1]
        else:
            assert isinstance(file_name, str) and len(file_name) > 0, (
                "File name must be a non-empty string! Can be omitted to use default file name."
            )
            fname, fext = os.path.splitext(file_name)
            assert len(fname) > 0 and fext.lower() == ".json", (
                "File name must be non-empty and of type .json!"
            )
        output_file = os.path.join(output_path, file_name)

        if not overwrite_if_exists:
            assert not os.path.exists(output_file), (
                f"Output file '{output_file}' already exists! Delete file or choose to overwrite."
            )

        with open(output_file, "w") as f:
            json.dump(sonata_circuit.node_sets.content, f, indent=2)

    def _resolve_ids(self, circuit, population):
        """Returns the full list of neuron IDs (w/o subsampling)."""
        c = circuit.sonata_circuit
        expression = self._get_expression(circuit, population)
        name = "__TMP_NODE_SET__"
        self.add_node_set_to_circuit(c, {name: expression})
        return c.nodes[population].ids(name)

    def get_neuron_ids(self, circuit, population):
        """Returns list of neuron IDs (with subsampling, if specified)."""
        self.enforce_no_lists()
        self.check_population(circuit, population)
        ids = np.array(self._resolve_ids(circuit, population))
        if self.random_sample is not None:
            np.random.seed(self.random_seed)

            if isinstance(self.random_sample, int):
                num_sample = np.minimum(self.random_sample, len(ids))
            elif isinstance(self.random_sample, float):
                num_sample = np.round(self.random_sample * len(ids)).astype(int)

            ids = ids[
                np.random.permutation([True] * num_sample + [False] * (len(ids) - num_sample))
            ]

        return ids

    def get_node_set_definition(self, circuit, population, force_resolve_ids=False):
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs."""
        self.enforce_no_lists()
        self.check_population(circuit, population)
        if self.random_sample is None and not force_resolve_ids:
            # Symbolic expression can be preserved
            expression = self._get_expression(circuit, population)
        else:
            # Individual IDs need to be resolved
            expression = {
                "population": population,
                "node_id": self.get_neuron_ids(circuit, population).tolist(),
            }

        return expression

    def to_node_set_file(
        self,
        circuit,
        population,
        output_path,
        file_name=None,
        overwrite_if_exists=False,
        append_if_exists=False,
        force_resolve_ids=False,
        init_empty=False,
    ):
        """Resolves the node set for a given circuit/population and writes it to a .json node set file."""
        assert self.name is not None, "NeuronSet name must be set!"
        if file_name is None:
            # Use circuit's node set file name by default
            file_name = os.path.split(circuit.sonata_circuit.config["node_sets_file"])[1]
        else:
            assert isinstance(file_name, str) and len(file_name) > 0, (
                "File name must be a non-empty string! Can be omitted to use default file name."
            )
            fname, fext = os.path.splitext(file_name)
            assert len(fname) > 0 and fext.lower() == ".json", (
                "File name must be non-empty and of type .json!"
            )
        output_file = os.path.join(output_path, file_name)

        assert not (overwrite_if_exists and append_if_exists), (
            "Append and overwrite options are mutually exclusive!"
        )

        expression = self.get_node_set_definition(
            circuit, population, force_resolve_ids=force_resolve_ids
        )
        assert expression is not None, "Node set already exists in circuit, nothing to be done!"

        if not os.path.exists(output_file) or overwrite_if_exists:
            # Create new node sets file, overwrite if existing
            if init_empty:
                # Initialize empty
                node_sets = {}
            else:
                # Initialize with circuit object's node sets
                node_sets = circuit.sonata_circuit.node_sets.content
                assert self.name not in node_sets, (
                    f"Node set '{self.name}' already exists in circuit '{circuit}'!"
                )
            node_sets.update({self.name: expression})

        elif os.path.exists(output_file) and append_if_exists:
            # Append to existing node sets file
            with open(output_file) as f:
                node_sets = json.load(f)
                assert self.name not in node_sets, (
                    f"Appending not possible, node set '{self.name}' already exists!"
                )
                node_sets.update({self.name: expression})

        else:  # File existing but no option chosen
            assert False, (
                f"Output file '{output_file}' already exists! Delete file or choose to append or overwrite."
            )

        with open(output_file, "w") as f:
            json.dump(node_sets, f, indent=2)

        return output_file


class PredefinedNeuronSet(NeuronSet):
    """Neuron set wrapper of an existing (named) node sets already predefined in the node sets file."""

    node_set: (
        Annotated[str, Field(min_length=1)]
        | Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    )

    def check_node_set(self, circuit, population):
        assert self.node_set in circuit.node_sets, (
            f"Node set '{self.node_set}' not found in circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [self.node_set]


class CombinedNeuronSet(NeuronSet):
    """Neuron set definition based on a combination of existing (named) node sets."""

    node_sets: (
        Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]
        | Annotated[
            list[Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]],
            Field(min_length=1),
        ]
    )

    def check_node_sets(self, circuit, population):
        for _nset in self.node_sets:  # Assumed that all (outer) lists have been resolved
            assert _nset in circuit.node_sets, (
                f"Node set '{_nset}' not found in circuit '{circuit}'!"
            )

    def _get_expression(self, circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_sets(circuit, population)
        return list(self.node_sets)


class IDNeuronSet(NeuronSet):
    """Neuron set definition by providing a list of neuron IDs."""

    neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)]

    def check_neuron_ids(self, circuit, population):
        popul_ids = circuit.sonata_circuit.nodes[population].ids()
        assert all(_nid in popul_ids for _nid in self.neuron_ids.elements), (
            f"Neuron ID(s) not found in population '{population}' of circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_neuron_ids(circuit, population)
        return {"population": population, "node_id": list(self.neuron_ids.elements)}


class PropertyNeuronSet(NeuronSet):
    """Neuron set definition based on neuron properties, optionally combined with (named) node sets."""

    property_specs: (
        Annotated[dict, Field(min_length=1)]
        | Annotated[list[Annotated[dict, Field(min_length=1)]], Field(min_length=1)]
    )
    node_sets: (
        tuple[Annotated[str, Field(min_length=1)], ...]
        | Annotated[list[tuple[Annotated[str, Field(min_length=1)], ...]], Field(min_length=1)]
    ) = tuple()

    def check_properties(self, circuit, population):
        prop_names = circuit.sonata_circuit.nodes[population].property_names
        assert all(_prop in prop_names for _prop in self.property_specs.keys()), (
            f"Invalid neuron properties! Available properties: {prop_names}"
        )  # Assumed that all (outer) lists have been resolved

    def check_node_sets(self, circuit, population):
        for _nset in self.node_sets:  # Assumed that all (outer) lists have been resolved
            assert _nset in circuit.node_sets, (
                f"Node set '{_nset}' not found in circuit '{circuit}'!"
            )

    def _get_expression(self, circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)
        if len(self.node_sets) == 0:
            # Symbolic expression can be preserved
            expression = self.property_specs
        else:
            # Individual IDs need to be resolved
            c = circuit.sonata_circuit
            node_ids = np.array([]).astype(int)
            for _nset in self.node_sets:  # Assumed that all (outer) lists have been resolved
                node_ids = np.union1d(node_ids, c.nodes[population].ids(_nset))
            node_ids = np.intersect1d(node_ids, c.nodes[population].ids(self.property_specs))

            expression = {"population": population, "node_id": node_ids.tolist()}

        return expression
