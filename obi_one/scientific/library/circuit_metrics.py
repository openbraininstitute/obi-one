import json
import os.path
import tempfile
from collections.abc import Iterator, Mapping
from enum import IntEnum, StrEnum, auto
from os.path import realpath
from pathlib import Path
from uuid import UUID

import numpy as np
import pandas as pd
from bluepysnap import Circuit as SnapCircuit
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy
from httpx import HTTPStatusError
from libsonata import (
    CircuitConfig,
    EdgePopulation,
    EdgeStorage,
    NodePopulation,
    NodeStorage,
)
from pydantic import BaseModel

ALL_POPULATIONS = "_ALL_"
TYPES_OF_CHEMICAL_SYNS = ["chemical", "Exp2Syn_synapse", "point_process"]
TYPES_OF_ELECTRICAL_SYNS = ["electrical"]
TYPES_OF_BIOPHYS_NODES = ["biophysical"]
TYPES_OF_VIRTUAL_NODES = ["point_process", "virtual"]


class NodePopulationType(StrEnum):
    biophysical = auto()
    virtual = auto()


class EdgePopulationType(StrEnum):
    chemical = auto()
    electrical = auto()


class SpatialCoordinate(StrEnum):
    x = auto()
    y = auto()
    z = auto()


class DegreeTypes(StrEnum):
    indegree = auto()
    outdegree = auto()
    totaldegree = auto()
    degreedifference = auto()


class CircuitStatsLevelOfDetail(IntEnum):
    none = 0
    basic = 1
    advanced = 2
    full = 3


MAX_UNIQUE_VALUES = {
    CircuitStatsLevelOfDetail.basic: 25,
    CircuitStatsLevelOfDetail.advanced: 50,
    CircuitStatsLevelOfDetail.full: 100,
}


def _assert_level_of_detail_specs(
    level_of_detail_nodes: dict[str, CircuitStatsLevelOfDetail] | None,
    level_of_detail_edges: dict[str, CircuitStatsLevelOfDetail] | None,
) -> tuple[dict[str, CircuitStatsLevelOfDetail], dict[str, CircuitStatsLevelOfDetail]]:
    if level_of_detail_nodes is None:
        level_of_detail_nodes = {ALL_POPULATIONS: CircuitStatsLevelOfDetail.none}
    if level_of_detail_edges is None:
        level_of_detail_edges = {ALL_POPULATIONS: CircuitStatsLevelOfDetail.none}
    if ALL_POPULATIONS not in level_of_detail_nodes:
        level_of_detail_nodes[ALL_POPULATIONS] = CircuitStatsLevelOfDetail.none
    if ALL_POPULATIONS not in level_of_detail_edges:
        level_of_detail_edges[ALL_POPULATIONS] = CircuitStatsLevelOfDetail.none
    for lod_edges in level_of_detail_edges.values():
        if lod_edges > CircuitStatsLevelOfDetail.basic:
            if CircuitStatsLevelOfDetail.none in level_of_detail_nodes.values():
                err_str = (
                    "To support more than basic level of detail on edges,"
                    " the minimum level of detail on nodes must be basic!"
                )
                raise ValueError(err_str)
            break
    return level_of_detail_nodes, level_of_detail_edges


class TemporaryAsset:
    def __init__(
        self, path_to_fetch: Path, db_client: Client, circuit_id: str, asset_id: str
    ) -> None:
        """Initialize TemporaryAsset."""
        self._remote_path = str(path_to_fetch)
        self._db_client = db_client
        self._circuit_id = circuit_id
        self._asset_id = asset_id

    def __enter__(self) -> Path:
        """Enter."""
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_file_path = Path(self.temp_dir.__enter__()) / os.path.split(self._remote_path)[1]

        try:
            self._db_client.fetch_file(
                entity_id=UUID(self._circuit_id),
                entity_type=Circuit,
                asset_id=UUID(self._asset_id),
                output_path=temp_file_path,
                asset_path=Path(self._remote_path),
                strategy=FetchFileStrategy.link_or_download,
            )
        except HTTPStatusError:
            self.temp_dir.__exit__(None, None, None)
            raise
        return temp_file_path

    def __exit__(self, *args) -> None:
        """Exit."""
        self.temp_dir.__exit__(*args)


def get_names_of_typed_populations(
    config: CircuitConfig, type_str: list[str], population_type: str
) -> list[str]:
    names = []
    if population_type == "edges":
        for pop_name in config.edge_populations:
            if config.edge_population_properties(pop_name).type in type_str:
                names.extend([pop_name])
    elif population_type == "nodes":
        for pop_name in config.node_populations:
            if config.node_population_properties(pop_name).type in type_str:
                names.extend([pop_name])
    else:
        err_str = f"Unknown population_type: {population_type}"
        raise ValueError(err_str)
    return names


def get_names_of_typed_node_populations(config: CircuitConfig, type_str: list[str]) -> list[str]:
    return get_names_of_typed_populations(config, type_str, "nodes")


def get_names_of_typed_edge_populations(config: CircuitConfig, type_str: list[str]) -> list[str]:
    return get_names_of_typed_populations(config, type_str, "edges")


def get_number_of_typed_node_populations(config: CircuitConfig, type_str: list[str]) -> int:
    return len(get_names_of_typed_node_populations(config, type_str))


def get_number_of_typed_edge_populations(config: CircuitConfig, type_str: list[str]) -> int:
    return len(get_names_of_typed_edge_populations(config, type_str))


def properties_from_config(config: CircuitConfig) -> dict:
    return {
        "number_of_biophys_node_populations": get_number_of_typed_node_populations(
            config, TYPES_OF_BIOPHYS_NODES
        ),
        "number_of_virtual_node_populations": get_number_of_typed_node_populations(
            config, TYPES_OF_VIRTUAL_NODES
        ),
        "number_of_chemical_edge_populations": get_number_of_typed_edge_populations(
            config, TYPES_OF_CHEMICAL_SYNS
        ),
        "number_of_electrical_edge_populations": get_number_of_typed_edge_populations(
            config, TYPES_OF_ELECTRICAL_SYNS
        ),
        "names_of_biophys_node_populations": get_names_of_typed_node_populations(
            config, TYPES_OF_BIOPHYS_NODES
        ),
        "names_of_virtual_node_populations": get_names_of_typed_node_populations(
            config, TYPES_OF_VIRTUAL_NODES
        ),
        "names_of_chemical_edge_populations": get_names_of_typed_edge_populations(
            config, TYPES_OF_CHEMICAL_SYNS
        ),
        "names_of_electrical_edge_populations": get_names_of_typed_edge_populations(
            config, TYPES_OF_ELECTRICAL_SYNS
        ),
    }


def names_from_node_sets_file(
    config: CircuitConfig,
    temp_dir: str,
    db_client: Client,
    circuit_id: str,
    asset_id: str | UUID,
) -> list:
    ns_path = realpath(config.node_sets_path)
    if len(ns_path) > 0:
        try:
            remote_path = Path(ns_path).relative_to(temp_dir)
            with (
                TemporaryAsset(remote_path, db_client, circuit_id, str(asset_id)) as fn,
                Path.open(fn) as fid,
            ):
                contents = json.load(fid)
        except EntitySDKError:
            # Error downloading the node sets file from directory asset
            contents = {}
    else:
        contents = {}
    return list(contents.keys())


def dynamics_params_from_population(pop: NodePopulation) -> list[str]:
    return list(pop.dynamics_attribute_names)


def unique_node_property_values_from_population(
    pop: NodePopulation,
    max_unique_values: int,
) -> dict[str, list]:
    return {
        name: pop.enumeration_values(name)
        for name in pop.enumeration_names
        if len(pop.enumeration_values(name)) <= max_unique_values
    }


def number_of_nodes_per_unique_value_from_population(
    pop: NodePopulation, max_unique_values: int
) -> dict:
    vals_dict = {}
    for name in pop.enumeration_names:
        prop_vals = pop.enumeration_values(name)
        if len(prop_vals) <= max_unique_values:
            prop_idx = pop.get_enumeration(name, pop.select_all())

            prop_counts = (
                pd.Series(prop_idx).value_counts().reindex(range(len(prop_vals)), fill_value=0)
            )
            prop_counts.index = prop_vals
            vals_dict[name] = prop_counts.to_dict()
    return vals_dict


def node_location_properties_from_population(pop: NodePopulation) -> dict:
    vals_dict = {}
    coord_names = [
        _coord
        for _coord in [SpatialCoordinate.x, SpatialCoordinate.y, SpatialCoordinate.z]
        if str(_coord) in pop.attribute_names
    ]
    for _coord in coord_names:
        coord_v = pop.get_attribute(_coord, pop.select_all())
        vals_dict[_coord] = {
            "min": np.min(coord_v),
            "max": np.max(coord_v),
            "mean": np.mean(coord_v),
            "median": np.median(coord_v),
            "middle": 0.5 * np.min(coord_v) + 0.5 * np.max(coord_v),
            "std": np.std(coord_v),
            "spread": np.max(coord_v) - np.min(coord_v),
        }
    return vals_dict


def edge_property_stats_from_population(pop: EdgePopulation) -> dict:
    vals_dict = {}
    for edgeprop_name in pop.attribute_names:
        if edgeprop_name in pop.enumeration_names:
            continue
        vals = pop.get_attribute(edgeprop_name, pop.select_all())
        vals_dict[edgeprop_name] = {
            "mean": np.mean(vals),
            "median": np.median(vals),
            "min": np.min(vals),
            "max": np.max(vals),
            "std": np.std(vals),
        }
    return vals_dict


def degree_stats_from_population(
    pop: EdgePopulation, node_stats_dict: dict
) -> dict[str, dict[str, float]]:
    sz = node_stats_dict[pop.target]["population_length"]
    indegs = np.array([pop.afferent_edges(_i).flat_size for _i in range(sz)])
    sz = node_stats_dict[pop.source]["population_length"]
    outdegs = np.array([pop.efferent_edges(_i).flat_size for _i in range(sz)])
    stats = {
        degtype: {
            "min": np.min(degs),
            "mean": np.mean(degs),
            "median": np.median(degs),
            "max": np.max(degs),
        }
        for degtype, degs in zip(
            [DegreeTypes.indegree, DegreeTypes.outdegree],
            [indegs, outdegs],
            strict=False,
        )
    }
    if len(indegs) == len(outdegs):
        ttldegs = indegs + outdegs
        degdiff = outdegs - indegs
        add_stats = {
            degtype: {
                "min": np.min(degs),
                "mean": np.mean(degs),
                "median": np.median(degs),
                "max": np.max(degs),
            }
            for degtype, degs in zip(
                [DegreeTypes.totaldegree, DegreeTypes.degreedifference],
                [ttldegs, degdiff],
                strict=False,
            )
        }
        stats.update(add_stats)
    return stats  # ty:ignore[invalid-return-type]


def properties_from_nodes_files(
    circ: SnapCircuit,
    temp_dir: str,
    db_client: Client,
    circuit_id: str,
    asset_id: str | UUID,
    level_of_detail_specs: dict[str, CircuitStatsLevelOfDetail],
) -> dict:
    default_lod = level_of_detail_specs[ALL_POPULATIONS]
    lst_req_props = [
        "population_length",
        "property_list",
        "property_unique_values",
        "property_value_counts",
    ]
    properties_dict = {}
    config = circ.to_libsonata
    for nodepop in get_names_of_typed_node_populations(
        config, TYPES_OF_VIRTUAL_NODES + TYPES_OF_BIOPHYS_NODES
    ):
        lod = level_of_detail_specs.get(nodepop, default_lod)
        if lod > CircuitStatsLevelOfDetail.none:
            np_file_path = circ.nodes[nodepop].h5_filepath
            remote_path = Path(np_file_path).relative_to(temp_dir)
            properties_dict[nodepop] = {_k: {} for _k in lst_req_props}
            max_uv = MAX_UNIQUE_VALUES[lod]
            with TemporaryAsset(remote_path, db_client, circuit_id, str(asset_id)) as fn:
                pop_obj = NodeStorage(fn).open_population(nodepop)
                properties_dict[nodepop]["population_length"] = pop_obj.size
                properties_dict[nodepop]["property_list"] = list(pop_obj.attribute_names)
                properties_dict[nodepop]["property_unique_values"] = (
                    unique_node_property_values_from_population(pop_obj, max_uv)
                )
                properties_dict[nodepop]["property_value_counts"] = (
                    number_of_nodes_per_unique_value_from_population(pop_obj, max_uv)
                )
                if nodepop in get_names_of_typed_node_populations(config, TYPES_OF_BIOPHYS_NODES):
                    properties_dict[nodepop]["dynamics_param_names"] = (
                        dynamics_params_from_population(pop_obj)
                    )
                if lod > CircuitStatsLevelOfDetail.basic:
                    properties_dict[nodepop]["node_location_info"] = (
                        node_location_properties_from_population(pop_obj)
                    )

    return properties_dict


def properties_from_edges_files(
    circ: SnapCircuit,
    temp_dir: str,
    node_stats_dict: dict,
    db_client: Client,
    circuit_id: str,
    asset_id: str | UUID,
    level_of_detail_specs: dict[str, CircuitStatsLevelOfDetail],
) -> dict:
    default_lod = level_of_detail_specs[ALL_POPULATIONS]
    lst_req_props = ["number_of_edges", "property_list", "property_stats", "degrees"]
    properties_dict = {}
    config = circ.to_libsonata
    for edgepop in get_names_of_typed_edge_populations(
        config, TYPES_OF_CHEMICAL_SYNS + TYPES_OF_ELECTRICAL_SYNS
    ):
        if level_of_detail_specs.get(edgepop, default_lod) > CircuitStatsLevelOfDetail.none:
            properties_dict[edgepop] = {_k: {} for _k in lst_req_props}

            ep_file_path = circ.edges[edgepop].h5_filepath
            remote_path = Path(ep_file_path).relative_to(temp_dir)
            with (
                TemporaryAsset(remote_path, db_client, circuit_id, str(asset_id)) as fn,
            ):
                pop_obj = EdgeStorage(fn).open_population(edgepop)
                properties_dict[edgepop]["number_of_edges"] = pop_obj.size
                properties_dict[edgepop]["property_list"] = list(pop_obj.attribute_names)
                properties_dict[edgepop]["source_name"] = pop_obj.source
                properties_dict[edgepop]["target_name"] = pop_obj.target
                if (
                    level_of_detail_specs.get(edgepop, default_lod)
                    > CircuitStatsLevelOfDetail.basic
                ):
                    properties_dict[edgepop]["property_stats"] = (
                        edge_property_stats_from_population(pop_obj)
                    )
                    properties_dict[edgepop]["degrees"] = degree_stats_from_population(
                        pop_obj, node_stats_dict
                    )
    return properties_dict


class CircuitMetricsNodePopulation(BaseModel):
    number_of_nodes: int
    name: str
    population_type: NodePopulationType
    property_names: list[str]
    property_unique_values: dict[str, list[str]]
    property_value_counts: dict[str, dict[str, int]]
    dynamics_param_names: list[str] | None = None
    node_location_info: dict[SpatialCoordinate, dict[str, float]] | None


class CircuitMetricsEdgePopulation(BaseModel):
    number_of_edges: int
    name: str
    population_type: EdgePopulationType
    source_name: str | None = None
    target_name: str | None = None
    property_names: list[str]
    property_stats: dict[str, dict[str, float]] | None
    degree_stats: dict[DegreeTypes, dict[str, float]] | None


class CircuitPopulationsResponse(BaseModel):
    populations: list[str]


class CircuitNodesetsResponse(BaseModel):
    nodesets: list[str]


class CircuitMetricsOutput(BaseModel, Mapping):
    number_of_biophys_node_populations: int
    number_of_virtual_node_populations: int
    names_of_biophys_node_populations: list[str]
    names_of_virtual_node_populations: list[str]
    names_of_nodesets: list[str]
    biophysical_node_populations: list[CircuitMetricsNodePopulation | None]
    virtual_node_populations: list[CircuitMetricsNodePopulation | None]
    number_of_chemical_edge_populations: int
    number_of_electrical_edge_populations: int
    names_of_chemical_edge_populations: list[str]
    names_of_electrical_edge_populations: list[str]
    chemical_edge_populations: list[CircuitMetricsEdgePopulation | None]
    electrical_edge_populations: list[CircuitMetricsEdgePopulation | None]

    def __iter__(self) -> Iterator[CircuitMetricsEdgePopulation | None]:  # ty:ignore[invalid-method-override]
        """Provides iterator over all populations (node + edge)."""
        yield from self.biophysical_node_populations + self.virtual_node_populations  # ty:ignore[invalid-yield]

    def __getitem__(
        self, key: str
    ) -> CircuitMetricsNodePopulation | CircuitMetricsEdgePopulation | None:
        """Provides access to populations by name."""
        if key in self.names_of_biophys_node_populations:
            return self.biophysical_node_populations[
                self.names_of_biophys_node_populations.index(key)
            ]
        if key in self.names_of_virtual_node_populations:
            return self.virtual_node_populations[self.names_of_virtual_node_populations.index(key)]
        if key in self.names_of_chemical_edge_populations:
            return self.chemical_edge_populations[
                self.names_of_chemical_edge_populations.index(key)
            ]
        if key in self.names_of_electrical_edge_populations:
            return self.electrical_edge_populations[
                self.names_of_electrical_edge_populations.index(key)
            ]
        msg = f"No node nor edge population {key}!"
        raise KeyError(msg)

    def __len__(self) -> int:
        """Returns total number of populations (node + edge)."""
        return self.number_of_biophys_node_populations + self.number_of_virtual_node_populations


def get_circuit_metrics(  # noqa: PLR0914
    circuit_id: str,
    db_client: Client,
    level_of_detail_nodes: dict[str, CircuitStatsLevelOfDetail] | None = None,
    level_of_detail_edges: dict[str, CircuitStatsLevelOfDetail] | None = None,
) -> CircuitMetricsOutput:
    level_of_detail_nodes, level_of_detail_edges = _assert_level_of_detail_specs(
        level_of_detail_nodes, level_of_detail_edges
    )
    circuit = db_client.get_entity(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
    )

    directory_assets = [
        a for a in circuit.assets if a.is_directory and a.label.value == "sonata_circuit"
    ]
    if len(directory_assets) != 1:
        error_msg = "Circuit must have exactly one directory asset."
        raise ValueError(error_msg)

    asset_id = directory_assets[0].id

    # db_client.download_content does not support `asset_path` at the time of writing this
    # Use db_client.fetch_file with temporary directory instead
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = Path(temp_dir) / "circuit_config.json"

        db_client.fetch_file(
            entity_id=UUID(circuit_id),
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=temp_file_path,
            asset_path=Path("circuit_config.json"),
            strategy=FetchFileStrategy.link_or_download,
        )

        circ = SnapCircuit(temp_file_path)
        config = circ.to_libsonata

    temp_dir = realpath(str(temp_dir))
    dict_props = properties_from_config(config)
    nodesets = names_from_node_sets_file(config, temp_dir, db_client, circuit_id, asset_id)

    node_props = properties_from_nodes_files(
        circ, temp_dir, db_client, circuit_id, asset_id, level_of_detail_nodes
    )
    edge_props = properties_from_edges_files(
        circ, temp_dir, node_props, db_client, circuit_id, asset_id, level_of_detail_edges
    )

    biophys_pops = []
    for nodepop in dict_props["names_of_biophys_node_populations"]:
        pop = None
        if nodepop in node_props:
            pop = CircuitMetricsNodePopulation(
                number_of_nodes=node_props[nodepop]["population_length"],
                name=nodepop,
                population_type=NodePopulationType.biophysical,
                property_names=node_props[nodepop]["property_list"],
                property_unique_values=node_props[nodepop]["property_unique_values"],
                property_value_counts=node_props[nodepop]["property_value_counts"],
                dynamics_param_names=node_props[nodepop]["dynamics_param_names"],
                # Use .get() because node_location_info is only added when level_of_detail > basic
                node_location_info=node_props[nodepop].get("node_location_info"),
            )
        biophys_pops.append(pop)
    virtual_pops = []
    for nodepop in dict_props["names_of_virtual_node_populations"]:
        pop = None
        if nodepop in node_props:
            pop = CircuitMetricsNodePopulation(
                number_of_nodes=node_props[nodepop]["population_length"],
                name=nodepop,
                population_type=NodePopulationType.virtual,
                property_names=node_props[nodepop]["property_list"],
                property_unique_values=node_props[nodepop]["property_unique_values"],
                property_value_counts=node_props[nodepop]["property_value_counts"],
                # Use .get() because node_location_info is only added when level_of_detail > basic
                node_location_info=node_props[nodepop].get("node_location_info"),
            )
        virtual_pops.append(pop)
    chemical_pops = []
    for edgepop in dict_props["names_of_chemical_edge_populations"]:
        pop = None
        if edgepop in edge_props:
            pop = CircuitMetricsEdgePopulation(
                number_of_edges=edge_props[edgepop]["number_of_edges"],
                name=edgepop,
                population_type=EdgePopulationType.chemical,
                source_name=edge_props[edgepop]["source_name"],
                target_name=edge_props[edgepop]["target_name"],
                property_names=edge_props[edgepop]["property_list"],
                property_stats=edge_props[edgepop]["property_stats"],
                degree_stats=edge_props[edgepop]["degrees"],
            )
        chemical_pops.append(pop)
    electrical_pops = []
    for edgepop in dict_props["names_of_electrical_edge_populations"]:
        pop = None
        if edgepop in edge_props:
            pop = CircuitMetricsEdgePopulation(
                number_of_edges=edge_props[edgepop]["number_of_edges"],
                name=edgepop,
                population_type=EdgePopulationType.electrical,
                source_name=edge_props[edgepop]["source_name"],
                target_name=edge_props[edgepop]["target_name"],
                property_names=edge_props[edgepop]["property_list"],
                property_stats=edge_props[edgepop]["property_stats"],
                degree_stats=edge_props[edgepop]["degrees"],
            )
        electrical_pops.append(pop)

    return CircuitMetricsOutput(
        number_of_biophys_node_populations=dict_props["number_of_biophys_node_populations"],
        number_of_virtual_node_populations=dict_props["number_of_virtual_node_populations"],
        number_of_chemical_edge_populations=dict_props["number_of_chemical_edge_populations"],
        number_of_electrical_edge_populations=dict_props["number_of_electrical_edge_populations"],
        names_of_biophys_node_populations=dict_props["names_of_biophys_node_populations"],
        names_of_virtual_node_populations=dict_props["names_of_virtual_node_populations"],
        names_of_chemical_edge_populations=dict_props["names_of_chemical_edge_populations"],
        names_of_electrical_edge_populations=dict_props["names_of_electrical_edge_populations"],
        names_of_nodesets=nodesets,
        biophysical_node_populations=biophys_pops,
        virtual_node_populations=virtual_pops,
        chemical_edge_populations=chemical_pops,
        electrical_edge_populations=electrical_pops,
    )
