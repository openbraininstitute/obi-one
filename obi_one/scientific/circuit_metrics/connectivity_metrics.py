import bluepysnap as snap
import numpy as np
import obi_one as obi
import pandas as pd
import tempfile
from entitysdk.client import Client
from entitysdk.models.circuit import Circuit
from entitysdk.types import uuid
from httpx import HTTPStatusError
from pydantic import BaseModel
from connectome_manipulator.connectome_comparison import connectivity


class ConnectivityMetricsOutput(BaseModel):
    pre_type: list[str | None] = [None]
    post_type: list[str | None] = [None]
    connection_probability: list[float] = [np.nan]
    mean_number_of_synapses: list[float] = [np.nan]


class TemporaryPartialCircuit:
    """Partial circuit downloaded to temporary folder.

    To avoid unnecessary data download, only the following circuit components are included:
    Circuit config, node sets, selected edges, src/tgt nodes of selected edges
    """
    def __init__(
        self, db_client: Client, circuit_id: str, edge_population: str
    ) -> None:
        """Initialize TemporaryPartialCircuit."""
        self._db_client = db_client
        self._circuit_id = circuit_id
        self._edge_population = edge_population

    def _download_file(self, rel_path: str) -> Path:
        temp_file_path = Path(self.temp_dir.name) / rel_path
        self._db_client.download_file(
            entity_id=self._circuit_id,
            entity_type=Circuit,
            asset_id=self.asset_id,
            output_path=temp_file_path,
            asset_path=rel_path,
        )
        return temp_file_path

    def _get_sonata_asset_id(self) -> uuid.UUID:
        circuit = self._db_client.get_entity(
            entity_id=self._circuit_id,
            entity_type=Circuit,
        )
        sonata_assets = [
            a for a in circuit.assets if a.is_directory and a.label.value == "sonata_circuit"
        ]
        if len(sonata_assets) != 1:
            msg = "Circuit must have exactly one SONATA circuit directory asset!"
            raise ValueError(msg)
        return sonata_assets[0].id

    def _get_edges_path(self, c: snap.Circuit) -> str:
        edges_list = c.config["networks"]["edges"]
        edges = [e for e in edges_list if self._edge_population in e["populations"]]
        if len(edges) != 1:
            msg = f"Edge population '{self._edge_population}' not found in the circuit!"
            raise ValueError(msg)
        return edges[0]["edges_file"]

    def _get_nodes_path(self, c: snap.Circuit, node_population: str) -> str:
        nodes_list = c.config["networks"]["nodes"]
        nodes = [n for n in nodes_list if node_population in n["populations"]]
        if len(nodes) != 1:
            msg = f"Node population '{node_population}' not found in the circuit!"
            raise ValueError(msg)
        return nodes[0]["nodes_file"]

    def __enter__(self) -> Path:
        """Enter."""
        self.asset_id = self._get_sonata_asset_id()
        self.temp_dir = tempfile.TemporaryDirectory()
        try:
            # Download circuit config
            rel_path = "circuit_config.json"
            circuit_config_file = self._download_file(rel_path)
            circuit = obi.Circuit(name=str(self._circuit_id), path=str(circuit_config_file))
            c = circuit.sonata_circuit

            # Download node sets file
            rel_path = Path(c.config["node_sets_file"]).relative_to(Path(self.temp_dir.name).resolve())
            self._download_file(rel_path)

            # Download edge population
            edges_path = self._get_edges_path(c)
            rel_path = Path(edges_path).relative_to(Path(self.temp_dir.name).resolve())
            self._download_file(rel_path)

            # Download src/tgt node populations
            src_nodes = c.edges[self._edge_population].source.name
            tgt_nodes = c.edges[self._edge_population].target.name
            for npop in np.unique([src_nodes, tgt_nodes]):
                nodes_path = self._get_nodes_path(c, npop)
                rel_path = Path(nodes_path).relative_to(Path(self.temp_dir.name).resolve())
                self._download_file(rel_path)
        except HTTPStatusError:
            self.temp_dir.__exit__(None, None, None)
            raise
        return circuit_config_file

    def __exit__(self, *args) -> None:
        """Exit."""
        self.temp_dir.__exit__(*args)


def _get_neuron_selection(circuit: obi.Circuit, node_population: str, neuron_set: obi.NeuronSet | None = None) -> list | None:
    if neuron_set is None:
        nrn_sel = None
    else:
        nrn_sel = neuron_set.get_neuron_ids(circuit, node_population)
    return nrn_sel


def _get_stacked_dataframe(conn_dict: dict, data_sel: str) -> pd.DataFrame:
    df = pd.DataFrame(conn_dict[data_sel]["data"], index=conn_dict["common"]["src_group_values"], columns=conn_dict["common"]["tgt_group_values"])
    df.index.name = "pre"
    df.columns.name = "post"
    return df.stack()


def get_connectivity_metrics(circuit_id: str, db_client: Client, edge_population: str, pre_neuron_set: obi.NeuronSet | None = None, post_neuron_set: obi.NeuronSet | None = None, group_by: str | None = None, max_distance: float | None = None) -> ConnectionProbabilityOutput:
    # Download partial circuit (incl. config, node sets, selected edges, src/tgt nodes of selected edges)
    with TemporaryPartialCircuit(db_client, circuit_id, edge_population) as cfg_path:
        # Load circuit
        circuit = obi.Circuit(name=circuit_id, path=str(cfg_path))
        c = circuit.sonata_circuit

        # Compute connection probability
        edges = c.edges[edge_population]
        src_sel = _get_neuron_selection(circuit, edges.source.name)
        tgt_sel = _get_neuron_selection(circuit, edges.target.name)
    
        if max_distance is None:
            dist_props = None
        else:
            dist_props = ["x", "y", "z"]

        conn_dict = connectivity.compute(c, sel_src=src_sel, sel_dest=tgt_sel, edges_popul_name=edge_population, group_by=group_by, max_distance=max_distance, props_for_distance=dist_props)

    # Return results
    df_prob = _get_stacked_dataframe(conn_dict, "conn_prob")
    df_nsyn = _get_stacked_dataframe(conn_dict, "nsyn_conn")
    conn_output = ConnectivityMetricsOutput(
        pre_type=df_prob.index.get_level_values("pre"),
        post_type=df_prob.index.get_level_values("post"),
        connection_probability=df_prob.to_numpy(),
        mean_number_of_synapses=df_nsyn.to_numpy()
    )

    return conn_output