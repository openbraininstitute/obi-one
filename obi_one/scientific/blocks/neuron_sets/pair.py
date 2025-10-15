import logging
from typing import Literal

import numpy as np
import pandas as pd
from conntility import ConnectivityMatrix
from pydantic import Field

from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")


class PairMotifNeuronSet(NeuronSet):
    """Neuron set selection based on pair motifs of neurons."""

    neuron1_filter: dict | list[dict] = Field(
        default={}, name="Neuron1 filter", description="Filter for first neuron in a pair"
    )
    neuron2_filter: dict | list[dict] = Field(
        default={}, name="Neuron2 filter", description="Filter for second neuron in a pair"
    )

    conn_ff_filter: dict | list[dict] = Field(
        default={},
        name="Feedforward connection filter",
        description="Filter for feedforward connections from the first to the second neuron"
        " in a pair",
    )
    conn_fb_filter: dict | list[dict] = Field(
        default={},
        name="Feedback connection filter",
        description="Filter for feedback connections from the second to the first neuron in a pair",
    )

    pair_selection: dict | list[dict] = Field(
        default={},
        name="Selection of pairs",
        description="Selection of pairs among all potential pairs",
    )

    node_set_list_op: Literal["union", "intersect"] = Field(
        default="union",
        name="Node set list operation",
        description="Operation how to combine lists of node sets; can be 'union' or 'intersect'.",
    )

    @staticmethod
    def _add_nsynconn_fb(conn_mat_filt: ConnectivityMatrix, conn_mat: ConnectivityMatrix) -> None:
        """Adds #syn/conn for reciprocal connections (i.e., in feedback direction) in-place.

        Note: Will be added even if they are not part of the filtered selection.
        """
        etab = conn_mat._edge_indices.copy()
        etab = etab.reset_index(drop=True)
        etab["nsyn_ff_"] = conn_mat._edges["nsyn_ff_"].to_numpy()
        etab["iloc_ff_"] = conn_mat._edges["iloc_ff_"].to_numpy()
        etab = etab.set_index(["row", "col"])

        etab_filt = conn_mat_filt._edge_indices.copy()
        etab_filt["nsyn_fb_"] = 0
        etab_filt["iloc_fb_"] = -1
        etab_filt = etab_filt.set_index(["row", "col"])

        rev_idx = etab_filt.index.swaplevel("row", "col").to_numpy()  # Reverse index
        etab_filt[["nsyn_fb_", "iloc_fb_"]] = etab.reindex(rev_idx, fill_value=-1).to_numpy()
        etab_filt.loc[etab_filt["nsyn_fb_"] < 0, "nsyn_fb_"] = 0

        conn_mat_filt.add_edge_property("nsyn_fb_", etab_filt["nsyn_fb_"])
        conn_mat_filt.add_edge_property("iloc_fb_", etab_filt["iloc_fb_"])

    @staticmethod
    def _merge_ff_fb(ff_sel: dict, fb_sel: dict) -> dict:
        sel = {}
        for _sel, _lbl in zip([ff_sel, fb_sel], ["_ff_", "_fb_"], strict=False):
            if _sel is not None:
                sel |= {f"{_k}{_lbl}": _v for _k, _v in _sel.items()}
        return sel

    @staticmethod
    def _apply_filter(
        conn_mat: ConnectivityMatrix, selection: dict, side: str | None = None
    ) -> ConnectivityMatrix:
        def _check_ops(ops: list) -> None:
            for _op in ops:
                if _op not in {"le", "lt", "ge", "gt", "eq", "isin"}:
                    msg = (
                        f"ERROR: Operator '{_op}' unknown (must be one of 'le', 'lt', 'ge', 'gt')!"
                    )
                    raise ValueError(msg)

        conn_mat_filt = conn_mat
        for _prop, _val in selection.items():
            op = "eq"  # Default: Filter by equality (i.e., single value is provided)
            val = _val
            if isinstance(val, list):  # List: Select all values from list
                op = "isin"
            elif isinstance(val, dict):  # Dict: Combinations of operator/value pairs
                op = list(val.keys())
                val = list(val.values())
            if not isinstance(op, list):
                op = [op]
                val = [val]
            _check_ops(op)
            for _o, _v in zip(op, val, strict=False):
                if (
                    _prop in conn_mat_filt.vertex_properties
                    and conn_mat_filt.vertices.dtypes[_prop] == "category"
                ):
                    v = str(_v)
                else:
                    v = _v
                conn_mat_filt = getattr(conn_mat_filt.filter(_prop, side), _o)(
                    v
                )  # Call filter operator
        return conn_mat_filt

    @staticmethod
    def _remove_autapses(conn_mat: ConnectivityMatrix) -> ConnectivityMatrix:
        sel_idx = (conn_mat._edge_indices["row"] != conn_mat._edge_indices["col"]).reset_index(
            drop=True
        )
        return conn_mat.subedges(
            conn_mat._edge_indices.reset_index(drop=True)[sel_idx].index.values
        )

    @staticmethod
    def _selected_pair_table(conn_mat_filt: ConnectivityMatrix) -> pd.DataFrame:
        pair_tab = conn_mat_filt._edge_indices.copy()
        pair_tab = pair_tab.reset_index(drop=True)
        pair_tab.columns = ["nrn1", "nrn2"]
        pair_tab["nsyn_ff"] = conn_mat_filt.edges["nsyn_ff_"].to_numpy()
        pair_tab["nsyn_fb"] = conn_mat_filt.edges["nsyn_fb_"].to_numpy()
        pair_tab["nsyn_all"] = pair_tab["nsyn_ff"] + pair_tab["nsyn_fb"]
        pair_tab["is_rc"] = pair_tab["nsyn_fb"] > 0
        return pair_tab

    @staticmethod
    def _select_pairs(
        conn_mat: ConnectivityMatrix, nrn1_sel: dict, nrn2_sel: dict, ff_sel: dict, fb_sel: dict
    ) -> pd.DataFrame:
        """Filter pairs based on neuron and connection properties.

        Neuron properties: synapse_class, mtype, layer, etc.
        Connection properties: nsyn (#synapses per connection)
        Note: ff...feed-forward direction (i.e., from nrn1 to nrn2)
              fb...feedback direction (i.e., from nrn2 to nrn1)
        """
        conn_mat_filt = conn_mat
        conn_mat_filt = PairMotifNeuronSet._apply_filter(conn_mat_filt, nrn1_sel, "row")
        conn_mat_filt = PairMotifNeuronSet._apply_filter(conn_mat_filt, nrn2_sel, "col")
        conn_mat_filt = PairMotifNeuronSet._remove_autapses(conn_mat_filt)
        PairMotifNeuronSet._add_nsynconn_fb(conn_mat_filt, conn_mat)
        conn_mat_filt = PairMotifNeuronSet._apply_filter(
            conn_mat_filt, PairMotifNeuronSet._merge_ff_fb(ff_sel, fb_sel)
        )
        pair_tab = PairMotifNeuronSet._selected_pair_table(conn_mat_filt)

        return pair_tab

    @staticmethod
    def _get_node_sets_ids(
        node_sets: dict, node_set_list_op: str, circuit: Circuit, population: str
    ) -> np.ndarray:
        nodes = circuit.sonata_circuit.nodes[population]
        if isinstance(node_sets, str):
            node_ids = nodes.ids(node_sets)
        elif isinstance(node_sets, list):  # Combine node sets
            node_ids = None
            for _nset in node_sets:
                if node_ids is None:
                    node_ids = nodes.ids(_nset)
                elif node_set_list_op == "union":
                    node_ids = np.union1d(node_ids, nodes.ids(_nset))
                elif node_set_list_op == "intersect":
                    node_ids = np.intersect1d(node_ids, nodes.ids(_nset))
                else:
                    msg = f"Node set list operation '{node_set_list_op}' unknown!"
                    raise ValueError(msg)
        return node_ids

    @staticmethod
    def _prepare_node_set_filter(
        conn_mat: ConnectivityMatrix,
        nrn1_sel: dict,
        nrn2_sel: dict,
        node_set_list_op: str,
        circuit: Circuit,
        population: str,
    ) -> tuple[dict, dict]:
        """Prepare filtering based on node sets.
        Note: Modifies the connectivity matrix in-place!
        """
        nrn1_sel = nrn1_sel.copy()
        nrn2_sel = nrn2_sel.copy()

        nset1 = nrn1_sel.pop("node_set", None)
        nset2 = nrn2_sel.pop("node_set", None)

        if nset1 is not None:
            nids1 = PairMotifNeuronSet._get_node_sets_ids(
                nset1, node_set_list_op, circuit, population
            )
            conn_mat.add_vertex_property("node_set1", np.isin(conn_mat.vertices["node_ids"], nids1))
            nrn1_sel.update({"node_set1": True})

        if nset2 is not None:
            nids2 = PairMotifNeuronSet._get_node_sets_ids(
                nset2, node_set_list_op, circuit, population
            )
            conn_mat.add_vertex_property("node_set2", np.isin(conn_mat.vertices["node_ids"], nids2))
            nrn2_sel.update({"node_set2": True})

        return nrn1_sel, nrn2_sel

    @staticmethod
    def _subsample_pairs(
        pair_tab: pd.DataFrame, pair_sel_count: int, pair_sel_method: str, pair_sel_seed: int
    ) -> pd.DataFrame:
        if pair_sel_count is None:
            return pair_tab

        if pair_sel_count < 0:
            msg = "Pair selection count cannot be negative!"
            raise ValueError(msg)

        if pair_sel_count == 0:  # Select none
            pair_sel_ids = np.array([])
        elif pair_sel_count >= pair_tab.shape[0]:  # Select all
            pair_sel_ids = pair_tab.index.to_numpy()
        elif pair_sel_method == "first":
            pair_sel_ids = pair_tab.index.to_numpy()[:pair_sel_count]
        elif pair_sel_method == "random":
            rng = np.random.default_rng(pair_sel_seed)
            pair_sel_ids = rng.choice(pair_tab.index.to_numpy(), pair_sel_count, replace=False)
        elif pair_sel_method.startswith("max_"):
            prop = pair_sel_method.split("_", maxsplit=1)[-1]
            val = pair_tab[f"{prop}"]
            val = val.iloc[np.argsort(val)[::-1]]
            pair_sel_ids = val.index.to_numpy()[:pair_sel_count]
        else:
            msg = f"Pair selection method '{pair_sel_method}' unknown!"
            raise ValueError(msg)

        # Filter pairs
        pair_tab = pair_tab.loc[pair_sel_ids]

        return pair_tab

    def get_pair_table(self, circuit: Circuit, population: str) -> pd.DataFrame:
        conn_mat = circuit.connectivity_matrix
        if conn_mat.is_multigraph:
            msg = "ERROR: ConnectivityMatrix must not be a multi-graph!"
            raise ValueError(msg)

        # Add new columns for feed-forward selection
        conn_mat.add_edge_property(
            "nsyn_ff_",
            conn_mat.edges[conn_mat._default_edge],
        )  # Default column expected to represent #synapses/connection
        conn_mat.add_edge_property(
            "iloc_ff_", np.arange(conn_mat.edges.shape[0])
        )  # Add iloc (position index) based on which to subselect edges later on

        # Prepare node set filtering
        nrn1_filter, nrn2_filter = PairMotifNeuronSet._prepare_node_set_filter(
            conn_mat,
            self.neuron1_filter,
            self.neuron2_filter,
            self.node_set_list_op,
            circuit,
            population,
        )

        # Get table with all potential pairs
        pair_tab = PairMotifNeuronSet._select_pairs(
            conn_mat, nrn1_filter, nrn2_filter, self.conn_ff_filter, self.conn_fb_filter
        )

        # Subsample/select among these pairs
        if len(self.pair_selection) > 0:
            pair_sel_count = self.pair_selection["count"]
            pair_sel_method = self.pair_selection.get("method", "first")
            pair_sel_seed = self.pair_selection.get("seed", 0)
            pair_tab = PairMotifNeuronSet._subsample_pairs(
                pair_tab, pair_sel_count, pair_sel_method, pair_sel_seed
            )

        if pair_tab.shape[0] == 0:
            L.warning("Pair table empty!")

        return pair_tab

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        # Get table of neuron pairs
        pair_tab = self.get_pair_table(circuit, population)

        # Resolve pairs into neuron set expression
        nrn_set_ids = np.unique(pair_tab[["nrn1", "nrn2"]])
        expression = {"population": population, "node_id": nrn_set_ids.tolist()}

        return expression
