import abc
import json
import os
from typing import Annotated, Self, Literal, Optional, ClassVar

import bluepysnap as snap
import numpy as np
import pandas
import logging
from pydantic import Field, NonNegativeFloat, NonNegativeInt, model_validator, field_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.circuit.circuit import Circuit

from obi_one.core.exception import OBIONE_Error

L = logging.getLogger("obi-one")
_NBS1_VPM_NODE_POP = "VPM"
_NBS1_POM_NODE_POP = "POm"
_RCA1_CA3_NODE_POP = "CA3_projections"

_ALL_NODE_SET = "All"
_EXCITATORY_NODE_SET = "Excitatory"
_INHIBITORY_NODE_SET = "Inhibitory"


class NeuronPropertyFilter(OBIBaseModel, abc.ABC):
    filter_dict: dict[str, list] = Field(
        name="Filter",
        description="Filter dictionary. Note as this is NOT a Block and the list here is \
                    not to support multi-dimensional parameters but to support a key-value pair \
                    with multiple values i.e. {'layer': ['2', '3']}}",
        default={},
    )

    @model_validator(mode="after")
    def check_filter_dict_values(self) -> Self:
        for key, values in self.filter_dict.items():
            assert isinstance(values, list) and len(values) >= 1, (
                f"Filter key '{key}' must have a non-empty list of values."
            )
        return self

    @property
    def filter_keys(self) -> list[str]:
        return list(self.filter_dict.keys())

    @property
    def filter_values(self) -> list[list]:
        return list(self.filter_dict.values())

    def filter(self, df_in, reindex=True) -> pandas.DataFrame:
        ret = df_in
        for filter_key, filter_value in self.filter_dict.items():
            filter_value = [str(_entry) for _entry in filter_value]
            vld = ret[filter_key].astype(str).isin(filter_value)
            ret = ret.loc[vld]
            if reindex:
                ret = ret.reset_index(drop=True)
        return ret

    def test_validity(self, circuit, node_population: str) -> None:
        circuit_prop_names = circuit.sonata_circuit.nodes[node_population].property_names
        # filter_keys = list(self.filter_dict.keys())

        assert all(_prop in circuit_prop_names for _prop in self.filter_keys), (
            f"Invalid neuron properties! Available properties: {circuit_prop_names}"
        )

    def __repr__(self) -> str:
        """Return a string representation of the NeuronPropertyFilter object."""
        if len(self.filter_dict) == 0:
            return "NoFilter"
        string_rep = ""
        for filter_key, filter_value in self.filter_dict.items():
            string_rep += f"{filter_key}="
            for value in filter_value:
                string_rep += f"{value},"
        return string_rep[:-1]  # Remove trailing comma and space


class AbstractNeuronSet(Block, abc.ABC):
    """Base class representing a neuron set which can be turned into a SONATA node set by either
    adding it to an existing SONATA circuit object (add_node_set_to_circuit) or writing it to a
    SONATA node set .json file (write_circuit_node_set_file).
    Whenever such a neuron set is used in a SimulationsForm, it must be added to its neuron_sets
    dictionary with the key being the name of the SONATA node set which will internally be set
    in simulation_level_name upon initialization of the SimulationsForm.
    """

    sample_percentage: Annotated[NonNegativeFloat, Field(le=100)] | Annotated[list[Annotated[NonNegativeFloat, Field(le=100)]], Field(min_length=1)] = Field(
        default=100.0,
        title="Sample (Percentage)",
        description="Percentage of neurons to sample between 0 and 100%",
        units='%'
    )

    sample_seed: int | list[int] = Field(
        default=1,
        title="Sample Seed",
        description="Seed for random sampling."
    )

    @abc.abstractmethod
    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""

    @staticmethod
    def check_population(circuit: Circuit, population: str) -> None:
        assert population in Circuit.get_node_population_names(circuit.sonata_circuit), (
            f"Node population '{population}' not found in circuit '{circuit}'!"
        )

    @staticmethod
    def add_node_set_to_circuit(
        sonata_circuit: snap.Circuit, node_set_dict, overwrite_if_exists=False
    ) -> None:
        """Adds the node set definition to a SONATA circuit object to make it accessible \
            (in-place).
        """
        existing_node_sets = sonata_circuit.node_sets.content
        if not overwrite_if_exists:
            for _k in node_set_dict.keys():
                assert _k not in existing_node_sets, f"Node set '{_k}' already exists!"
        existing_node_sets.update(node_set_dict)
        sonata_circuit.node_sets = snap.circuit.NodeSets.from_dict(existing_node_sets)

    @staticmethod
    def write_circuit_node_set_file(
        sonata_circuit: snap.Circuit, output_path, file_name=None, overwrite_if_exists=False
    ) -> None:
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
    
    def _population(self, population: str | None=None):
        assert population is not None, "Must specify a node population name!"
        return population

    def _resolve_ids(self, circuit: Circuit, population: str | None=None) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        population = self._population(population)
        c = circuit.sonata_circuit
        expression = self._get_expression(circuit, population)
        name = "__TMP_NODE_SET__"
        self.add_node_set_to_circuit(c, {name: expression})
        return c.nodes[population].ids(name)

    def get_neuron_ids(self, circuit: Circuit, population: str | None=None):
        """Returns list of neuron IDs (with subsampling, if specified)."""
        self.enforce_no_lists()
        population = self._population(population)
        self.check_population(circuit, population)
        ids = np.array(self._resolve_ids(circuit, population))
        if len(ids) > 0 and self.sample_percentage < 100.0:
            rng = np.random.default_rng(self.sample_seed)

            num_sample = np.round((self.sample_percentage/100.0) * len(ids)).astype(int)

            ids = ids[
                rng.permutation([True] * num_sample + [False] * (len(ids) - num_sample))
            ]

        return ids

    def get_node_set_definition(
        self, circuit: Circuit, population: str | None=None, force_resolve_ids=False
    ) -> dict:
        """Returns the SONATA node set definition, optionally forcing to resolve individual \
            IDs.
        """
        self.enforce_no_lists()
        population = self._population(population)
        self.check_population(circuit, population)
        if self.sample_percentage is None and not force_resolve_ids:
            # Symbolic expression can be preserved
            expression = self._get_expression(circuit, population)
        else:
            # Individual IDs need to be resolved
            expression = {
                "population": population,
                "node_id": self.get_neuron_ids(circuit, population).tolist(),
            }

        return expression
    
    def population_type(self, circuit: Circuit, population: str | None=None):
        """Returns the population type (i.e. biophysical / virtual)."""
        return circuit.sonata_circuit.nodes[self._population(population)].type

    def to_node_set_file(
        self,
        circuit: Circuit,
        population,
        output_path,
        file_name=None,
        overwrite_if_exists=False,
        append_if_exists=False,
        force_resolve_ids=False,
        init_empty=False,
        optional_node_set_name=None,
    ):
        """Resolves the node set for a given circuit/population and writes it to a .json node \
            set file.
        """
        if optional_node_set_name is not None:
            self.set_simulation_level_name(optional_node_set_name)
        assert self.name is not None, "NeuronSet name must be set through the Simulation or optional_node_set_name parameter!"

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
        population = self._population(population)
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
                f"Output file '{output_file}' already exists! Delete file or choose to append \
                    or overwrite."
            )

        with open(output_file, "w") as f:
            json.dump(node_sets, f, indent=2)

        return output_file


class NeuronSet(AbstractNeuronSet):
    """
    Extension of abstract neuron set with the ability to specify the node population upon creation.
    This is optional, all functions requiring a node population can be optionally called with the name of
    a default population to be used in case no name was set upon creation.
    """
    node_population: str | list[str] | None = None

    def _population(self, population: str | None=None):
        if population is not None and self.node_population is not None:
            if population != self.node_population:
                L.warning("Node population %s has been set for this block and will be used. Ignoring %s",
                          self.node_population, population)
        population = self.node_population or population
        if population is None:
            raise ValueError("Must specify name of a node population to resolve the NeuronSet!")
        return population
    

class PredefinedNeuronSet(NeuronSet):
    """Neuron set wrapper of an existing (named) node sets already predefined in the node \
        sets file.
    """

    node_set: (
        Annotated[str, Field(min_length=1)]
        | Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    )

    def check_node_set(self, circuit: Circuit, population: str) -> None:
        assert self.node_set in circuit.node_sets, (
            f"Node set '{self.node_set}' not found in circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit: Circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [self.node_set]


class AllNeurons(AbstractNeuronSet):
    """All biophysical neurons."""

    title: ClassVar[str] = "All Neurons"
    
    def check_node_set(self, circuit: Circuit, population: str) -> None:
        assert _ALL_NODE_SET in circuit.node_sets, (
            f"Node set '{_ALL_NODE_SET}' not found in circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit: Circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_ALL_NODE_SET]


class ExcitatoryNeurons(AbstractNeuronSet):
    """All biophysical excitatory neurons."""

    title: ClassVar[str] = "All Excitatory Neurons"

    def check_node_set(self, circuit: Circuit, population: str) -> None:
        assert _EXCITATORY_NODE_SET in circuit.node_sets, (
            f"Node set '{_EXCITATORY_NODE_SET}' not found in circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit: Circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_EXCITATORY_NODE_SET]


class InhibitoryNeurons(AbstractNeuronSet):
    """All inhibitory neurons."""

    title: ClassVar[str] = "All Inhibitory Neurons"

    def check_node_set(self, circuit: Circuit, population: str) -> None:
        assert _INHIBITORY_NODE_SET in circuit.node_sets, (
            f"Node set '{_INHIBITORY_NODE_SET}' not found in circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit: Circuit, population):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_INHIBITORY_NODE_SET]


class nbS1VPMInputs(AbstractNeuronSet):
    """Virtual neurons projecting from the VPM thalamic nucleus to biophysical cortical neurons in the nbS1 model."""

    title: ClassVar[str] = "Demo: nbS1 VPM Inputs"
    
    def _population(self, population: str | None=None):
        # Ignore default node population name. This is always VPM.
        return _NBS1_VPM_NODE_POP
    
    def _get_expression(self, circuit: Circuit, population):
        return {"population": _NBS1_VPM_NODE_POP}
    

class nbS1POmInputs(AbstractNeuronSet):
    """Virtual neurons projecting from the POm thalamic nucleus to biophysical cortical neurons in the nbS1 model."""

    title: ClassVar[str] = "Demo: nbS1 POm Inputs"
    
    def _population(self, population: str | None=None):
        # Ignore default node population name. This is always POm.
        return _NBS1_POM_NODE_POP
    
    def _get_expression(self, circuit: Circuit, population):
        return {"population": _NBS1_POM_NODE_POP}


class rCA1CA3Inputs(AbstractNeuronSet):
    """Virtual neurons projecting from the CA3 region to biophysical CA1 neurons in the rCA1 model."""

    title: ClassVar[str] = "Demo: rCA1 CA3 Inputs"
    
    def _population(self, population: str | None=None):
        # Ignore default node population name. This is always CA3_projections.
        return _RCA1_CA3_NODE_POP
    
    def _get_expression(self, circuit: Circuit, population):
        return {"population": _RCA1_CA3_NODE_POP}
    

class CombinedNeuronSet(NeuronSet):
    """Neuron set definition based on a combination of existing (named) node sets."""

    node_sets: (
        Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]
        | Annotated[
            list[Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]],
            Field(min_length=1),
        ]
    )

    def check_node_sets(self, circuit: Circuit, population: str) -> None:
        for _nset in self.node_sets:  # Assumed that all (outer) lists have been resolved
            assert _nset in circuit.node_sets, (
                f"Node set '{_nset}' not found in circuit '{circuit}'!"
            )

    def _get_expression(self, circuit: Circuit, population: str):
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_sets(circuit, population)
        return list(self.node_sets)


class IDNeuronSet(AbstractNeuronSet):
    """Neuron set definition by providing a list of neuron IDs."""

    title: ClassVar[str] = "ID Neuron Set"

    neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)]

    def check_neuron_ids(self, circuit: Circuit, population) -> None:
        popul_ids = circuit.sonata_circuit.nodes[population].ids()
        assert all(_nid in popul_ids for _nid in self.neuron_ids.elements), (
            f"Neuron ID(s) not found in population '{population}' of circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit: Circuit, population) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        population = self._population(population)
        self.check_neuron_ids(circuit, population)
        return {"population": population, "node_id": list(self.neuron_ids.elements)}


class PropertyNeuronSet(NeuronSet):
    """Neuron set definition based on neuron properties, optionally combined with (named) node \
        sets.
    """

    property_filter: NeuronPropertyFilter | list[NeuronPropertyFilter] = Field(
        name="Neuron property filter",
        description="NeuronPropertyFilter object or list of NeuronPropertyFilter objects",
        default=(),
    )
    node_sets: (
        tuple[Annotated[str, Field(min_length=1)], ...]
        | Annotated[list[tuple[Annotated[str, Field(min_length=1)], ...]], Field(min_length=1)]
    ) = tuple()

    def check_properties(self, circuit: Circuit, population: str | None=None) -> None:
        population = self._population(population)
        self.property_filter.test_validity(circuit, population)

    def check_node_sets(self, circuit: Circuit, population: str) -> None:
        for _nset in self.node_sets:  # Assumed that all (outer) lists have been resolved
            assert _nset in circuit.node_sets, (
                f"Node set '{_nset}' not found in circuit '{circuit}'!"
            )

    def _get_resolved_expression(self, circuit: Circuit, population: str | None=None) -> dict:
        """A helper function used to make subclasses work."""
        c = circuit.sonata_circuit
        population = self._population(population)

        df = c.nodes[population].get(properties=self.property_filter.filter_keys).reset_index()
        df = self.property_filter.filter(df)

        node_ids = df["node_ids"].values

        if len(self.node_sets) > 0:
            node_ids_nset = np.array([]).astype(int)
            for _nset in self.node_sets:
                node_ids_nset = np.union1d(node_ids_nset, c.nodes[population].ids(_nset))
            node_ids = np.intersect1d(node_ids, node_ids_nset)

        expression = {"population": population, "node_id": node_ids.tolist()}
        return expression

    def _get_expression(self, circuit: Circuit, population) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        population = self._population(population)
        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)

        def __resolve_sngl(prop_vals):
            if len(prop_vals) == 1:
                return prop_vals[0]
            return list(prop_vals)

        if len(self.node_sets) == 0:
            # Symbolic expression can be preserved
            expression = dict(
                [
                    (property_key, __resolve_sngl(property_value))
                    for property_key, property_value in self.property_filter.filter_dict.items()
                ]
            )
        else:
            # Individual IDs need to be resolved
            return self._get_resolved_expression(circuit, population)

        return expression


class VolumetricCountNeuronSet(PropertyNeuronSet):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."""

    ox: float | list[float] = Field(
        name="Offset: x",
        description="Offset of the center of the volume, relative to the centroid of the node \
            population",
    )
    oy: float | list[float] = Field(
        name="Offset: y",
        description="Offset of the center of the volume, relative to the centroid of the node \
            population",
    )
    oz: float | list[float] = Field(
        name="Offset: z",
        description="Offset of the center of the volume, relative to the centroid of the node \
            population",
    )
    n: NonNegativeInt | list[NonNegativeInt] = Field(
        name="Number of neurons", description="Number of neurons to find"
    )
    columns_xyz: tuple[str, str, str] | list[tuple[str, str, str]] = Field(
        name="x/y/z column names",
        description="Names of the three neuron (node) properties used for volumetric tests",
        default=("x", "y", "z"),
    )

    def _get_expression(self, circuit: Circuit, population: str | None=None) -> dict:
        population = self._population(population)
        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)
        # Always needs to be resolved
        base_expression = self._get_resolved_expression(circuit, population)

        cols_xyz = list(self.columns_xyz)
        df = circuit.sonata_circuit.nodes[population].get(
            base_expression["node_id"], properties=cols_xyz
        )
        df = df.reset_index(drop=False)
        o_df = pandas.Series({cols_xyz[0]: self.ox, cols_xyz[1]: self.oy, cols_xyz[2]: self.oz})
        tgt_center = df[cols_xyz].mean() + o_df

        D = np.linalg.norm(df[cols_xyz] - tgt_center, axis=1)
        idxx = np.argsort(D)[: self.n]
        df = df.iloc[idxx]

        expression = {"population": population, "node_id": list(df["node_ids"].astype(int))}
        return expression

class SimplexMembershipBasedNeuronSet(PropertyNeuronSet):
    """
    Sample neurons from the set of neurons that form simplices of a given dimension with a chosen source or target 'central' neuron.
    """
    central_neuron_id: int = Field(
        name="Central neuron id",
        description="Node id (index) that will be source or target of the simplices extracted",
    )
    dim: int = Field(
        name="Dimension",
        description="Dimension of the simplices to be extracted",
    )
    central_neuron_simplex_position: Literal['source', 'target'] = Field('source',
        name="Central neuron simplex position",
        description="Position of the central neuron/node in the simplex, it can be either 'source' or 'target'",
    )
    subsample: bool = Field(True,
        name="subsample",
        description="Whether to subsample the set of nodes in the simplex lists or not",
    )
    n_count_max: Optional[int] = Field(False,
        name="Max node count",
        description="Maximum number of nodes to be subsampled",
    )
    subsample_method: Literal['node_participation', 'random'] = Field('node_participation',
        name="Method to subsample nodes from the extracted simplices",
        description="""
        **Method to subsample nodes**:
        - `random`: randomly selects nodes from all nodes in the simplices
        - `node_participation`: selects nodes with highest node participation 
            """,
    )
    simplex_type: Literal['directed', 'reciprocal', 'undirected'] = Field('directed',
        name="Simplex type",
        description="Type of simplex to consider. See more at \
            https://openbraininstitute.github.io/connectome-analysis/network_topology/#src.connalysis.network.topology.simplex_counts",
    )
    seed: Optional[int] = Field(None,
        name="seed",
        description="Seed used for random subsampling method",
    )

    @field_validator('dim')
    def dim_check(cls, v):
        if v <= 1:
            raise ValueError('Simplex dimension must be greater than 1')
        return v
    @model_validator(mode="after")
    def check_n_count_max(self) -> Self:
        n_count_max = self.n_count_max
        if self.subsample and n_count_max is None:
            raise ValueError("n_count_max must be specified when subsample is True")
        return self

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        try: # Try to import connalysis
            from obi_one.scientific.circuit.simplex_extractors import (simplex_submat)
        except ImportError as e:
            print(f"Import failed: {e}. You probably need to install connalysis locally")

        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)
        # Always needs to be resolved
        base_expression = self._get_resolved_expression(circuit, population)

        # Restrict connectivity matrix to chosen subpopulation and find index of center
        conn=circuit.connectivity_matrix.subpopulation(base_expression["node_id"])
        index = np.where(conn.vertices["node_ids"] == self.central_neuron_id)[0]
        if len(index) == 0:
            raise ValueError(f"The neuron of index {self.central_neuron_id} is not in the subpopulation selected")
        index = index[0]    
            
        # Get nodes on simplices index by 0 ... conn._shape[0] 
        out = simplex_submat(
            conn.matrix, index, self.dim, self.central_neuron_simplex_position,
            self.subsample, self.n_count_max, self.subsample_method,
            self.simplex_type, self.seed
        )
        selection = out[0] if self.subsample else out

        # Get node_ids (i.e., get correct index) and build expression dict 
        selection=conn.vertices["node_ids"].iloc[selection]
        expression = {"population": population, "node_id": selection.tolist()}        
        return expression
    

class SimplexNeuronSet(PropertyNeuronSet):
    """
    Get neurons that form simplices of a given dimension with a chosen source or target neuron.
    If a smaller sample is required, it samples simplices while the number of nodes on them is still 
    smaller or equal than a set target size.
    """
    central_neuron_id: int = Field(
        name="Central neuron id",
        description="Node id (index) that will be source or target of the simplices extracted",
    )
    dim: int = Field(
        name="Dimension",
        description="Dimension of the simplices to be extracted",
    )
    central_neuron_simplex_position: Literal['source', 'target'] = Field('source',
        name="Central neuron simplex position",
        description="Position of the central neuron/node in the simplex, it can be either 'source' or 'target'",
    )
    subsample: bool = Field(False,
        name="subsample",
        description="Whether to subsample the set of nodes in the simplex lists or not",
    )
    n_count_max: Optional[int] = Field(None,
        name="Max node count",
        description="Maximum number of nodes to be subsampled",
    )
    simplex_type: Literal['directed', 'reciprocal', 'undirected'] = Field('directed',
        name="Simplex type",
        description="Type of simplex to consider. See more at \
            https://openbraininstitute.github.io/connectome-analysis/network_topology/#src.connalysis.network.topology.simplex_counts",
    )
    seed: Optional[int] = Field(None,
        name="seed",
        description="Seed used for random subsampling method",
    )

    @field_validator('dim')
    def dim_check(cls, v):
        if v <= 1:
            raise ValueError('Simplex dimension must be greater than 1')
        return v
    @model_validator(mode="after")
    def check_n_count_max(self) -> Self:
        n_count_max = self.n_count_max
        if self.subsample and n_count_max is None:
            raise ValueError("n_count_max must be specified when subsample is True")
        return self

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        try: # Try to import connalysis
            from obi_one.scientific.circuit.simplex_extractors import (simplex_submat)
        except ImportError as e:
            print(f"Import failed: {e}. You probably need to install connalysis locally")

        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)
        # Always needs to be resolved
        base_expression = self._get_resolved_expression(circuit, population)

        # Restrict connectivity matrix to chosen subpopulation and find index of center
        conn=circuit.connectivity_matrix.subpopulation(base_expression["node_id"])
        index = np.where(conn.vertices["node_ids"] == self.central_neuron_id)[0]
        if len(index) == 0:
            raise ValueError(f"The neuron of index {self.central_neuron_id} is not in the subpopulation selected")
        index = index[0]    
            
        # Get nodes on simplices index by 0 ... conn._shape[0] 
        out = simplex_submat(
            conn.matrix, index, self.dim, self.central_neuron_simplex_position,
            self.subsample, self.n_count_max, 'sample_simplices',
            self.simplex_type, self.seed
        )
        selection = out[0] if self.subsample else out

        # Get node_ids (i.e., get correct index) and build expression dict 
        selection=conn.vertices["node_ids"].iloc[selection]
        expression = {"population": population, "node_id": selection.tolist()}        
        return expression
    



class VolumetricRadiusNeuronSet(PropertyNeuronSet):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."""

    ox: float | list[float] = Field(
        name="Offset: x",
        description="Offset of the center of the volume, relative to the centroid of the node \
            population",
    )
    oy: float | list[float] = Field(
        name="Offset: y",
        description="Offset of the center of the volume, relative to the centroid of the node \
            population",
    )
    oz: float | list[float] = Field(
        name="Offset: z",
        description="Offset of the center of the volume, relative to the centroid of the node \
            population",
    )
    radius: NonNegativeFloat | list[NonNegativeFloat] = Field(
        name="Radius", description="Radius in um of volumetric sample"
    )
    columns_xyz: tuple[str, str, str] | list[tuple[str, str, str]] = Field(
        name="x/y/z column names",
        description="Names of the three neuron (node) properties used for volumetric tests",
        default=("x", "y", "z"),
    )

    def _get_expression(self, circuit: Circuit, population: str | None=None) -> dict:
        population = self._population(population)
        self.check_node_sets(circuit, population)
        # Always needs to be resolved
        base_expression = self._get_resolved_expression(circuit, population)

        cols_xyz = list(self.columns_xyz)
        df = circuit.sonata_circuit.nodes[population].get(
            base_expression["node_id"], properties=cols_xyz
        )
        df = df.reset_index(drop=False)
        o_df = pandas.Series({cols_xyz[0]: self.ox, cols_xyz[1]: self.oy, cols_xyz[2]: self.oz})
        tgt_center = df[cols_xyz].mean() + o_df

        D = np.linalg.norm(df[cols_xyz] - tgt_center, axis=1)
        idxx = np.nonzero(self.radius > D)[0]
        df = df.iloc[idxx]

        expression = {"population": population, "node_id": list(df["node_ids"].astype(int))}
        return expression
