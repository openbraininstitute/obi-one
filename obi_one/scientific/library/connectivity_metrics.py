import os
import tempfile
from pathlib import Path
from typing import Annotated

import bluepysnap as snap
import numpy as np
import pandas as pd
from connectome_manipulator.connectome_comparison import connectivity
from entitysdk.client import Client
from entitysdk.models import Asset
from entitysdk.models.circuit import Circuit
from httpx import HTTPStatusError
from pydantic import BaseModel, Field
from pydantic.types import PositiveFloat

import obi_one as obi


class ConnectivityMetricsRequest(BaseModel):
    circuit_id: str
    edge_population: Annotated[
        str, Field(description="Name of the edge population to extract connectivity metrics from")
    ]
    pre_selection: Annotated[
        dict[str, str | list[str]] | None,
        Field(description="Property/value pairs for pre-synaptic neuron selection"),
    ] = None
    pre_node_set: Annotated[
        str | None, Field(description="Existing node set to apply pre-synaptic neuron selection in")
    ] = None
    post_selection: Annotated[
        dict[str, str | list[str]] | None,
        Field(description="Property/value pairs for post-synaptic neuron selection"),
    ] = None
    post_node_set: Annotated[
        str | None,
        Field(description="Existing node set to apply post-synaptic neuron selection in"),
    ] = None
    group_by: Annotated[str | None, Field(description="Property name to group connectivity by")] = (
        None
    )
    max_distance: Annotated[
        PositiveFloat | None,
        Field(description="Maximum distance (in um) to take connectivity into account"),
    ] = None


class ConnectivityMetricsOutput(BaseModel):
    connection_probability: (
        Annotated[
            dict,
            Field(
                description="Connection probabilities (in percent) between pre- and"
                " post-synaptic types as dict representation of a dataframe"
            ),
        ]
        | None
    ) = None
    mean_number_of_synapses: (
        Annotated[
            dict,
            Field(
                description="Mean numbers of synapses per connection between pre- and"
                " post-synaptic types as dict representation of a dataframe"
            ),
        ]
        | None
    ) = None


class TemporaryPartialCircuit:
    """Access mounted circuit if possible. Otherwise, download partial circuit to temporary folder.

    To avoid unnecessary data download, only the following circuit components are included:
    Circuit config, node sets, selected edges, src/tgt nodes of selected edges
    """

    def __init__(self, db_client: Client, circuit_id: str, edge_population: str) -> None:
        """Initialize TemporaryPartialCircuit."""
        self._db_client = db_client
        self._circuit_id = circuit_id
        self._edge_population = edge_population

    def _download_file(self, rel_path: str) -> Path:
        temp_file_path = Path(self.temp_dir.name) / rel_path
        self._db_client.download_file(
            entity_id=self._circuit_id,
            entity_type=Circuit,
            asset_id=self.asset.id,
            output_path=temp_file_path,
            asset_path=rel_path,
        )
        return temp_file_path

    def _get_sonata_asset(self) -> Asset:
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
        return sonata_assets[0]

    def _get_edges_path(self, c: snap.Circuit) -> str:
        edges_list = c.config["networks"]["edges"]
        edges = [e for e in edges_list if self._edge_population in e["populations"]]
        if len(edges) != 1:
            msg = f"Edge population '{self._edge_population}' not found in the circuit!"
            raise ValueError(msg)
        return edges[0]["edges_file"]

    @staticmethod
    def _get_nodes_path(c: snap.Circuit, node_population: str) -> str:
        nodes_list = c.config["networks"]["nodes"]
        nodes = [n for n in nodes_list if node_population in n["populations"]]
        if len(nodes) != 1:
            msg = f"Node population '{node_population}' not found in the circuit!"
            raise ValueError(msg)
        return nodes[0]["nodes_file"]

    def __enter__(self) -> Path:
        """Enter."""
        self.temp_dir = None
        self.asset = self._get_sonata_asset()

        # Try circuit mount
        config_fn = "circuit_config.json"
        mount_base_dir = os.environ.get("MOUNT_BASE_DIR")
        if mount_base_dir is not None:
            if self.asset.full_path.startswith("public/"):
                storage_type = "aws_s3_internal"
            else:
                storage_type = "aws_s3_open"
            # TODO: storage_type could be replaced by self.asset.storage_type once available
            #       in entitysdk
            circuit_config_file = (
                Path(mount_base_dir) / storage_type / self.asset.full_path / config_fn
            )
            if circuit_config_file.is_file():
                return circuit_config_file

        # Otherwise, download circuit in temp directory
        self.temp_dir = tempfile.TemporaryDirectory()
        try:
            # Download circuit config
            circuit_config_file = self._download_file(config_fn)
            circuit = obi.Circuit(name=str(self._circuit_id), path=str(circuit_config_file))
            c = circuit.sonata_circuit

            # Download node sets file
            rel_path = Path(c.config["node_sets_file"]).relative_to(
                Path(self.temp_dir.name).resolve()
            )
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
        if self.temp_dir is not None:
            self.temp_dir.__exit__(*args)


def _get_stacked_dataframe(conn_dict: dict, data_sel: str) -> pd.DataFrame:
    df = pd.DataFrame(conn_dict[data_sel]["data"], columns=conn_dict["common"]["tgt_group_values"])
    df["pre"] = conn_dict["common"]["src_group_values"]
    df = df.melt("pre", var_name="post", value_name="data")
    return df


def get_connectivity_metrics(
    circuit_id: str,
    db_client: Client,
    edge_population: str,
    pre_selection: dict | None = None,
    pre_node_set: str | None = None,
    post_selection: dict | None = None,
    post_node_set: str | None = None,
    group_by: str | None = None,
    max_distance: float | None = None,
) -> ConnectivityMetricsOutput:
    # Acces mounted circuit if possible, or download partial circuit otherwise
    # (incl. config, node sets, selected edges, src/tgt nodes of selected edges)
    with TemporaryPartialCircuit(db_client, circuit_id, edge_population) as cfg_path:
        # Load circuit
        circuit = obi.Circuit(name=circuit_id, path=str(cfg_path))
        c = circuit.sonata_circuit

        # Compute connection probability
        pre_dict = pre_selection | {"node_set": pre_node_set}
        post_dict = post_selection | {"node_set": post_node_set}
        dist_props = None if max_distance is None else ["x", "y", "z"]
        conn_dict = connectivity.compute(
            c,
            sel_src=pre_dict,
            sel_dest=post_dict,
            edges_popul_name=edge_population,
            group_by=group_by,
            max_distance=max_distance,
            props_for_distance=dist_props,
            skip_empty_groups=True,
        )

    # Return results
    df_prob = _get_stacked_dataframe(conn_dict, "conn_prob")
    df_nsyn = _get_stacked_dataframe(conn_dict, "nsyn_conn")
    conn_output = ConnectivityMetricsOutput(
        connection_probability=df_prob.to_dict(),
        mean_number_of_synapses=df_nsyn.to_dict(),
    )
    return conn_output
