import abc
import json
import os
from typing import Annotated, Self

import bluepysnap as snap
import numpy as np
import pandas
from pydantic import Field, model_validator, NonNegativeInt

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.core.tuple import NamedTuple


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
            vld = ret[filter_key].isin(filter_value)
            ret = ret.loc[vld]
            if reindex:
                ret = ret.reset_index(drop=True)
        return ret

    def test_validity(self, circuit, node_population: str) -> None:
        circuit_prop_names = circuit.sonata_circuit.nodes[node_population].property_names
        filter_keys = list(self.filter_dict.keys())

        assert all(_prop in circuit_prop_names for _prop in self.filter_keys), (
            f"Invalid neuron properties! Available properties: {prop_names}"
        )

    def __repr__(self) -> str:
        """Return a string representation of the NeuronPropertyFilter object."""
        if len(self.filter_dict) == 0:
            return "NoFilter"
        else:
            string_rep = ""
            for filter_key, filter_value in self.filter_dict.items():
                string_rep += f"{filter_key}="
                for value in filter_value:
                    string_rep += f"{value},"
            return string_rep[:-1]  # Remove trailing comma and space


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

    def check_simulation_init(self) -> None:
        assert self.simulation_level_name is not None, (
            f"'{self.__class__.__name__}' initialization within a simulation required!"
        )

    @abc.abstractmethod
    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""

    @property
    def name(self) -> str:
        self.check_simulation_init()
        return self.simulation_level_name

    @staticmethod
    def check_population(circuit: Circuit, population: str) -> None:
        assert population in circuit.get_node_population_names(), (
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

    def _resolve_ids(self, circuit: Circuit, population: str) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        c = circuit.sonata_circuit
        expression = self._get_expression(circuit, population)
        name = "__TMP_NODE_SET__"
        self.add_node_set_to_circuit(c, {name: expression})
        return c.nodes[population].ids(name)

    def get_neuron_ids(self, circuit: Circuit, population: str):
        """Returns list of neuron IDs (with subsampling, if specified)."""
        self.enforce_no_lists()
        self.check_population(circuit, population)
        ids = np.array(self._resolve_ids(circuit, population))
        if len(ids) > 0 and self.random_sample is not None:
            np.random.seed(self.random_seed)

            if isinstance(self.random_sample, int):
                num_sample = np.minimum(self.random_sample, len(ids))
            elif isinstance(self.random_sample, float):
                num_sample = np.round(self.random_sample * len(ids)).astype(int)

            ids = ids[
                np.random.permutation([True] * num_sample + [False] * (len(ids) - num_sample))
            ]

        return ids

    def get_node_set_definition(
        self, circuit: Circuit, population: str, force_resolve_ids=False
    ) -> dict:
        """Returns the SONATA node set definition, optionally forcing to resolve individual \
            IDs.
        """
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
        circuit: Circuit,
        population,
        output_path,
        file_name=None,
        overwrite_if_exists=False,
        append_if_exists=False,
        force_resolve_ids=False,
        init_empty=False,
    ):
        """Resolves the node set for a given circuit/population and writes it to a .json node \
            set file.
        """
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
                f"Output file '{output_file}' already exists! Delete file or choose to append \
                    or overwrite."
            )

        with open(output_file, "w") as f:
            json.dump(node_sets, f, indent=2)

        return output_file


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


class IDNeuronSet(NeuronSet):
    """Neuron set definition by providing a list of neuron IDs."""

    neuron_ids: NamedTuple | Annotated[list[NamedTuple], Field(min_length=1)]

    def check_neuron_ids(self, circuit: Circuit, population) -> None:
        popul_ids = circuit.sonata_circuit.nodes[population].ids()
        assert all(_nid in popul_ids for _nid in self.neuron_ids.elements), (
            f"Neuron ID(s) not found in population '{population}' of circuit '{circuit}'!"
        )  # Assumed that all (outer) lists have been resolved

    def _get_expression(self, circuit: Circuit, population) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
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

    def check_properties(self, circuit: Circuit, population: str) -> None:
        self.property_filter.test_validity(circuit, population)

    def check_node_sets(self, circuit: Circuit, population: str) -> None:
        for _nset in self.node_sets:  # Assumed that all (outer) lists have been resolved
            assert _nset in circuit.node_sets, (
                f"Node set '{_nset}' not found in circuit '{circuit}'!"
            )

    def _get_resolved_expression(self, circuit: Circuit, population: str) -> dict:
        """A helper function used to make subclasses work."""
        c = circuit.sonata_circuit

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
    n: NonNegativeInt | list[NonNegativeInt] = Field(name="Number of neurons", description="Number of neurons to find")
    columns_xyz: tuple[str, str, str] | list[tuple[str, str, str]] = Field(
        name="x/y/z column names",
        description="Names of the three neuron (node) properties used for volumetric tests",
        default=("x", "y", "z"),
    )

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
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


class VolumetricRadiusNeuronSet(PropertyNeuronSet):
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
    radius: float | list[float] = Field(
        name="Radius", description="Radius in um of volumetric sample"
    )
    columns_xyz: tuple[str, str, str] | list[tuple[str, str, str]] = Field(
        name="x/y/z column names",
        description="Names of the three neuron (node) properties used for volumetric tests",
        default=("x", "y", "z"),
    )

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
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
