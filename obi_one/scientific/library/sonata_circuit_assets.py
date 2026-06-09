"""Helpers for staging selected files from a SONATA circuit directory asset."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import bluepysnap as snap
import numpy as np
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy
from httpx import HTTPStatusError

if TYPE_CHECKING:
    from entitysdk.client import Client
    from entitysdk.models import Asset


def asset_path_relative_to(path: str | Path, parent_dir: str | Path) -> Path:
    """Convert a resolved local SONATA path back to its directory-asset path."""
    return Path(path).resolve().relative_to(Path(parent_dir).resolve())


def get_sonata_circuit_asset(db_client: Client, circuit_id: str) -> tuple[Circuit, Asset]:
    """Return a circuit entity and its unique sonata_circuit directory asset."""
    circuit = db_client.get_entity(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
    )
    sonata_assets = [
        asset
        for asset in circuit.assets
        if asset.is_directory and asset.label.value == "sonata_circuit"
    ]
    if len(sonata_assets) != 1:
        msg = "Circuit must have exactly one sonata_circuit directory asset."
        raise ValueError(msg)
    return circuit, sonata_assets[0]


class TemporarySonataCircuit:
    """Stage selected files from a SONATA circuit directory asset into a temp layout."""

    def __init__(
        self,
        db_client: Client,
        circuit_id: str,
        *,
        asset_id: UUID | None = None,
        edge_population: str | None = None,
        include_node_sets: bool = True,
        node_populations: list[str] | tuple[str, ...] = (),
    ) -> None:
        """Initialize the staged circuit context."""
        self._db_client = db_client
        self._circuit_id = circuit_id
        self._asset_id = asset_id
        self._edge_population = edge_population
        self._include_node_sets = include_node_sets
        self._node_populations = node_populations

    @property
    def temp_dir_path(self) -> Path:
        """Return the active temporary circuit directory path."""
        return Path(self.temp_dir.name).resolve()

    def fetch_file(self, rel_path: str | Path) -> Path:
        """Fetch a directory-asset file into the corresponding temp circuit path."""
        temp_file_path = self.temp_dir_path / rel_path
        temp_file_path.parent.mkdir(parents=True, exist_ok=True)
        if self._asset_id is None:
            msg = "Asset must have an id."
            raise ValueError(msg)
        self._db_client.fetch_file(
            entity_id=UUID(self._circuit_id),
            entity_type=Circuit,
            asset_id=self._asset_id,
            output_path=temp_file_path,
            asset_path=Path(rel_path),
            strategy=FetchFileStrategy.link_or_download,
        )
        return temp_file_path

    def _get_sonata_asset(self) -> Asset:
        return get_sonata_circuit_asset(self._db_client, self._circuit_id)[1]

    @staticmethod
    def get_edges_path(circuit: snap.Circuit, edge_population: str) -> str:
        """Return the edge HDF5 path for a SONATA edge population."""
        edges = [
            edge
            for edge in circuit.config["networks"]["edges"]
            if edge_population in edge["populations"]
        ]
        if len(edges) != 1:
            msg = f"Edge population '{edge_population}' not found in the circuit."
            raise ValueError(msg)
        return edges[0]["edges_file"]

    @staticmethod
    def get_nodes_path(circuit: snap.Circuit, node_population: str) -> str:
        """Return the node HDF5 path for a SONATA node population."""
        nodes = [
            node
            for node in circuit.config["networks"]["nodes"]
            if node_population in node["populations"]
        ]
        if len(nodes) != 1:
            msg = f"Node population '{node_population}' not found in the circuit."
            raise ValueError(msg)
        return nodes[0]["nodes_file"]

    def fetch_node_sets(self, circuit: snap.Circuit) -> Path | None:
        """Fetch the node sets file referenced by a SONATA config, if present."""
        node_sets_path = circuit.config.get("node_sets_file")
        if not node_sets_path:
            return None
        rel_path = asset_path_relative_to(node_sets_path, self.temp_dir_path)
        return self.fetch_file(rel_path)

    def fetch_node_population(self, circuit: snap.Circuit, node_population: str) -> Path:
        """Fetch the HDF5 file backing a node population."""
        nodes_path = self.get_nodes_path(circuit, node_population)
        rel_path = asset_path_relative_to(nodes_path, self.temp_dir_path)
        return self.fetch_file(rel_path)

    def fetch_edge_population(self, circuit: snap.Circuit, edge_population: str) -> Path:
        """Fetch the HDF5 file backing an edge population."""
        edges_path = self.get_edges_path(circuit, edge_population)
        rel_path = asset_path_relative_to(edges_path, self.temp_dir_path)
        return self.fetch_file(rel_path)

    def __enter__(self) -> Path:
        """Stage the requested partial circuit and return the config path."""
        if self._asset_id is None:
            self._asset_id = self._get_sonata_asset().id
        self.temp_dir = tempfile.TemporaryDirectory()

        try:
            circuit_config_file = self.fetch_file("circuit_config.json")
            circuit = snap.Circuit(circuit_config_file)
            if self._include_node_sets:
                self.fetch_node_sets(circuit)

            if self._edge_population is not None:
                self.fetch_edge_population(circuit, self._edge_population)
                edge = circuit.edges[self._edge_population]
                for node_population in np.unique([edge.source.name, edge.target.name]):
                    self.fetch_node_population(circuit, node_population)

            for node_population in self._node_populations:
                self.fetch_node_population(circuit, node_population)
        except HTTPStatusError:
            self.temp_dir.__exit__(None, None, None)
            raise
        return circuit_config_file

    def __exit__(self, *args: object) -> None:
        """Clean up the staged circuit directory."""
        if self.temp_dir is not None:
            self.temp_dir.__exit__(*args)
