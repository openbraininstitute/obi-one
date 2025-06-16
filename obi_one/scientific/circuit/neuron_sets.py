import abc
import json
import os
from typing import Annotated, Self

import bluepysnap as snap
import numpy as np
import pandas
import logging
from pydantic import Field, NonNegativeFloat, NonNegativeInt, model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.circuit.circuit import Circuit


L = logging.getLogger("obi-one")
_NBS1_VPM_NODE_POP = "VPM"
_NBS1_POM_NODE_POP = "POm"
_RCA1_CA3_NODE_POP = "CA3_projections"

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
        if len(ids) > 0 and self.random_sample is not None:
            rng = np.random.default_rng(self.random_seed)

            if isinstance(self.random_sample, int):
                num_sample = np.minimum(self.random_sample, len(ids))
            elif isinstance(self.random_sample, float):
                num_sample = np.round(self.random_sample * len(ids)).astype(int)

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


class nbS1VPMInputs(AbstractNeuronSet):
    
    def _population(self, population: str | None=None):
        # Ignore default node population name. This is always VPM.
        return _NBS1_VPM_NODE_POP
    
    def _get_expression(self, circuit: Circuit, population):
        return {"population": _NBS1_VPM_NODE_POP}
    

class nbS1POmInputs(AbstractNeuronSet):
    
    def _population(self, population: str | None=None):
        # Ignore default node population name. This is always POm.
        return _NBS1_POM_NODE_POP
    
    def _get_expression(self, circuit: Circuit, population):
        return {"population": _NBS1_POM_NODE_POP}


class rCA1CA3Inputs(AbstractNeuronSet):
    
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


class PairMotifNeuronSet(NeuronSet):
    neuron1_filter: dict | list[dict] = Field(default={}, name="Neuron1 filter", description="Filter for first neuron in a pair")
    neuron2_filter: dict | list[dict] = Field(default={}, name="Neuron2 filter", description="Filter for second neuron in a pair")

    conn_ff_filter: dict | list[dict] = Field(default={}, name="Feedforward connection filter", description="Filter for feedforward connections from the first to the second neuron in a pair")
    conn_fb_filter: dict | list[dict] = Field(default={}, name="Feedback connection filter", description="Filter for feedback connections from the second to the first neuron in a pair")

    pair_selection: dict | list[dict] = Field(default={}, name="Selection of pairs", description="Selection of pairs among all potential pairs")

    @staticmethod
    def _add_nsynconn_fb(conn_mat_filt, conn_mat):
        """Adds #syn/conn for reciprocal connections (i.e., in feedback direction) even if they are not part of the filtered selection."""
        etab = conn_mat._edge_indices.copy()
        etab.reset_index(drop=True, inplace=True)
        etab["nsyn_ff_"] = conn_mat._edges["nsyn_ff_"].values
        etab["iloc_ff_"] = conn_mat._edges["iloc_ff_"].values
        etab.set_index(["row", "col"], inplace=True)
    
        etab_filt = conn_mat_filt._edge_indices.copy()
        etab_filt["nsyn_fb_"] = 0
        etab_filt["iloc_fb_"] = -1
        etab_filt.set_index(["row", "col"], inplace=True)
    
        for _idx in etab_filt.index:
            _ridx = _idx[::-1]  # Reverse index
            if _ridx in etab.index:
                etab_filt.loc[_idx, "nsyn_fb_"] = etab.loc[_ridx, "nsyn_ff_"]
                etab_filt.loc[_idx, "iloc_fb_"] = etab.loc[_ridx, "iloc_ff_"]
        conn_mat_filt.add_edge_property("nsyn_fb_", etab_filt["nsyn_fb_"])
        conn_mat_filt.add_edge_property("iloc_fb_", etab_filt["iloc_fb_"])

    @staticmethod
    def _merge_ff_fb(ff_sel, fb_sel):
        sel = {}
        for _sel, _lbl in zip([ff_sel, fb_sel], ["_ff_", "_fb_"]):
            if _sel is not None:
                sel = sel | {f"{_k}{_lbl}": _v for _k, _v in _sel.items()}
        return sel

    @staticmethod
    def _apply_filter(conn_mat, selection, side=None):
        def _check_ops(ops):
            for _op in ops:
                assert _op in ["le", "lt", "ge", "gt", "eq", "isin"], f"ERROR: Operator '{_op}' unknown (must be one of 'le', 'lt', 'ge', 'gt')!"
        conn_mat_filt = conn_mat
        for _prop, _val in selection.items():
            _op = "eq"  # Default: Filter by equality (i.e., single value is provided)
            if isinstance(_val, list):  # List: Select all values from list
                _op = "isin"
            elif isinstance(_val, dict):  # Dict: Combinations of operator/value pairs
                _op = list(_val.keys())
                _val = list(_val.values())
            if not isinstance(_op, list):
                _op = [_op]
                _val = [_val]
            _check_ops(_op)
            for _o, _v in zip(_op, _val):
                conn_mat_filt = getattr(conn_mat_filt.filter(_prop, side), _o)(_v)  # Call filter operator
        return conn_mat_filt

    @staticmethod
    def _remove_autapses(conn_mat):
        sel_idx = (conn_mat._edge_indices["row"] != conn_mat._edge_indices["col"]).reset_index(drop=True)
        return conn_mat.subedges(conn_mat._edge_indices.reset_index(drop=True)[sel_idx].index.values)

    @staticmethod
    def _selected_pair_table(conn_mat_filt):
        pair_tab = conn_mat_filt._edge_indices.copy()
        pair_tab.reset_index(drop=True, inplace=True)
        pair_tab.columns = ["nrn1", "nrn2"]
        pair_tab["nsyn_ff"] = conn_mat_filt.edges["nsyn_ff_"].values
        pair_tab["nsyn_fb"] = conn_mat_filt.edges["nsyn_fb_"].values
        pair_tab["nsyn_all"] = pair_tab["nsyn_ff"] + pair_tab["nsyn_fb"]
        pair_tab["is_rc"] = pair_tab["nsyn_fb"] > 0
        return pair_tab
    
    @staticmethod
    def _select_pairs(conn_mat, nrn1_sel, nrn2_sel, ff_sel, fb_sel):
        """Filter pairs based on neuron and connection properties.
             Neuron properties: synapse_class, mtype, layer, etc.
             Connection properties: nsyn (#synapses per connection)
             Note: ff...feed-forward direction (i.e., from nrn1 to nrn2), fb...feedback direction (i.e., from nrn2 to nrn1)
        """
        conn_mat_filt = conn_mat
        conn_mat_filt = PairMotifNeuronSet._apply_filter(conn_mat_filt, nrn1_sel, "row")
        conn_mat_filt = PairMotifNeuronSet._apply_filter(conn_mat_filt, nrn2_sel, "col")
        conn_mat_filt = PairMotifNeuronSet._remove_autapses(conn_mat_filt)
        PairMotifNeuronSet._add_nsynconn_fb(conn_mat_filt, conn_mat)
        conn_mat_filt = PairMotifNeuronSet._apply_filter(conn_mat_filt, PairMotifNeuronSet._merge_ff_fb(ff_sel, fb_sel))
        pair_tab = PairMotifNeuronSet._selected_pair_table(conn_mat_filt)
    
        # print(f"<select_pairs>: {pair_tab.shape[0]} pairs selected ({np.sum(pair_tab['is_rc'] == True)} reciprocal, {np.sum(pair_tab['is_rc'] == False)} feedforward only)")
    
        return pair_tab

    @staticmethod
    def _prepare_node_set_filter(conn_mat, nrn1_sel: dict, nrn2_sel: dict, circuit: Circuit, population: str):
        """Prepare filtering based on node sets.
           Note: Modifies the connectivity matrix in-place!
        """
        nrn1_sel = nrn1_sel.copy()
        nrn2_sel = nrn2_sel.copy()

        nset1 = nrn1_sel.pop("node_set", None)
        nset2 = nrn2_sel.pop("node_set", None)

        if nset1 is not None:
            nids1 = circuit.sonata_circuit.nodes[population].ids(nset1)
            conn_mat.add_vertex_property("node_set1", np.isin(conn_mat.vertices["node_ids"], nids1))
            nrn1_sel.update({"node_set1": True})

        if nset2 is not None:
            nids2 = circuit.sonata_circuit.nodes[population].ids(nset2)
            conn_mat.add_vertex_property("node_set2", np.isin(conn_mat.vertices["node_ids"], nids2))
            nrn2_sel.update({"node_set2": True})

        return nrn1_sel, nrn2_sel

    def get_pair_table(self, circuit: Circuit, population: str) -> pandas.DataFrame:
        conn_mat = circuit.connectivity_matrix
        assert np.array_equal(conn_mat.vertices.index, circuit.sonata_circuit.nodes[population].ids()), "ERROR: Neuron ID mismatch in ConnectivityMatrix!"
        assert np.array_equal(conn_mat.edges.columns, ["data"]), "ERROR: Single edge property 'data' expected (containing the synapse counts)!"
        conn_mat.edges.columns = ["nsyn_ff_"]  # Rename to represent #synapses/connection in feedforward connection
        conn_mat.add_edge_property("iloc_ff_", np.arange(conn_mat.edges.shape[0]))  # Add iloc (position index) based on which to subselect edges later on

        # Prepare node set filtering
        nrn1_filter, nrn2_filter = PairMotifNeuronSet._prepare_node_set_filter(conn_mat, self.neuron1_filter, self.neuron2_filter, circuit, population)
        
        # Get table with all potential pairs
        pair_tab = PairMotifNeuronSet._select_pairs(conn_mat, nrn1_filter, nrn2_filter, self.conn_ff_filter, self.conn_fb_filter)

        # Subsample/select among these pairs
        if len(self.pair_selection) > 0:
            pair_sel_count = self.pair_selection["count"]
            pair_sel_method = self.pair_selection.get("method", "first")
            pair_sel_seed = self.pair_selection.get("seed", 0)

            assert pair_sel_count >= 0, "Pair selection count cannot be negative!"

            if pair_sel_count is not None:
                if pair_sel_count <= 0:  # Select none
                    pair_sel_ids = np.array([])
                elif pair_sel_count >= pair_tab.shape[0]:  # Select all
                    pair_sel_ids = pair_tab.index.to_numpy()
                else:
                    if pair_sel_method == "first":
                        pair_sel_ids = pair_tab.index.to_numpy()[:pair_sel_count]
                    elif pair_sel_method == "random":
                        rng = np.random.default_rng(pair_sel_seed)
                        pair_sel_ids = rng.choice(pair_tab.index.to_numpy(), pair_sel_count, replace=False)
                    elif pair_sel_method.startswith("max_"):
                        _prop = pair_sel_method.split("_", maxsplit=1)[-1]
                        _val = pair_tab[f"{_prop}"]
                        _val = _val.iloc[np.argsort(_val)[::-1]]
                        pair_sel_ids = _val.index.to_numpy()[:pair_sel_count]
                    else:
                        assert False, f"Pair selection method '{pair_sel_method}' unknown!"
                
                # Filter pairs
                pair_tab = pair_tab.loc[pair_sel_ids]

        return pair_tab

    def _get_expression(self, circuit: Circuit, population: str) -> dict:

        # Get table of neuron pairs
        pair_tab = self.get_pair_table(circuit, population)

        # Resolve pairs into neuron set expression
        nrn_set_ids = np.unique(pair_tab[["nrn1", "nrn2"]])
        expression = {"population": population, "node_id": nrn_set_ids.tolist()}

        return expression