import json
import os.path
import tempfile
from collections.abc import Iterator, Mapping
from enum import IntEnum, StrEnum, auto
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from entitysdk.client import Client
from entitysdk.models.circuit import Circuit
from httpx import HTTPStatusError
from pydantic import BaseModel

ALL_POPULATIONS = "_ALL_"


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


def _get_asset_path(config_path: str, manifest: dict, temp_dir: str) -> Path:
    for k, v in manifest.items():
        config_path = config_path.replace(k, v)
    path_to_fetch = Path(config_path).relative_to(temp_dir)
    return path_to_fetch


def _assert_level_of_detail_specs(
    level_of_detail_nodes: dict, level_of_detail_edges: dict
) -> tuple:
    if level_of_detail_nodes is None:
        level_of_detail_nodes = {ALL_POPULATIONS: CircuitStatsLevelOfDetail.none}
    if level_of_detail_edges is None:
        level_of_detail_edges = {ALL_POPULATIONS: CircuitStatsLevelOfDetail.none}
    if ALL_POPULATIONS not in level_of_detail_nodes:
        level_of_detail_nodes[ALL_POPULATIONS] = CircuitStatsLevelOfDetail.none
    if ALL_POPULATIONS not in level_of_detail_edges:
        level_of_detail_edges[ALL_POPULATIONS] = CircuitStatsLevelOfDetail.none
    return level_of_detail_nodes, level_of_detail_edges


class CircuitStatsLevelOfDetail(IntEnum):
    none = 0
    basic = 1
    advanced = 2
    full = 3


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
            self._db_client.download_file(
                entity_id=self._circuit_id,
                entity_type=Circuit,
                asset_id=self._asset_id,
                output_path=temp_file_path,
                asset_path=self._remote_path,
            )
        except HTTPStatusError:
            self.temp_dir.__exit__(None, None, None)
            raise
        return temp_file_path

    def __exit__(self, *args) -> None:
        """Exit."""
        self.temp_dir.__exit__(*args)


def get_names_of_typed_populations(
    config_dict: dict, type_str: str, population_type: str
) -> list[str]:
    names = []
    lst_nodes = config_dict.get("networks", {}).get(population_type, [])
    for nodefile in lst_nodes:
        for population_name, population in nodefile["populations"].items():
            if population["type"] == type_str:
                names.append((nodefile[f"{population_type}_file"], population_name))
    return names


def get_names_of_typed_node_populations(config_dict: dict, type_str: str) -> list[str]:
    return get_names_of_typed_populations(config_dict, type_str, "nodes")


def get_names_of_typed_edge_populations(config_dict: dict, type_str: str) -> list[str]:
    return get_names_of_typed_populations(config_dict, type_str, "edges")


def get_number_of_typed_node_populations(config_dict: dict, type_str: str) -> int:
    return len(get_names_of_typed_node_populations(config_dict, type_str))


def get_number_of_typed_edge_populations(config_dict: dict, type_str: str) -> int:
    return len(get_names_of_typed_edge_populations(config_dict, type_str))


def properties_from_config(config_dict: dict) -> dict:
    return {
        "number_of_biophys_node_populations": get_number_of_typed_node_populations(
            config_dict, "biophysical"
        ),
        "number_of_virtual_node_populations": get_number_of_typed_node_populations(
            config_dict, "virtual"
        ),
        "number_of_chemical_edge_populations": get_number_of_typed_edge_populations(
            config_dict, "chemical"
        ),
        "number_of_electrical_edge_populations": get_number_of_typed_edge_populations(
            config_dict, "electrical"
        ),
        "names_of_biophys_node_populations": get_names_of_typed_node_populations(
            config_dict, "biophysical"
        ),
        "names_of_virtual_node_populations": get_names_of_typed_node_populations(
            config_dict, "virtual"
        ),
        "names_of_chemical_edge_populations": get_names_of_typed_edge_populations(
            config_dict, "chemical"
        ),
        "names_of_electrical_edge_populations": get_names_of_typed_edge_populations(
            config_dict, "electrical"
        ),
    }


def names_from_node_sets_file(
    config_dict: dict,
    manifest: dict,
    temp_dir: str,
    db_client: Client,
    circuit_id: str,
    asset_id: str,
) -> list:
    remote_path = _get_asset_path(config_dict["node_sets_file"], manifest, temp_dir)
    with TemporaryAsset(remote_path, db_client, circuit_id, asset_id) as fn, Path.open(fn) as fid:
        contents = json.load(fid)
    return list(contents.keys())


def number_of_nodes_from_h5(h5: h5py.File, population_name: str) -> int:
    return len(h5["nodes"][population_name]["node_type_id"])


def number_of_edges_from_h5(h5: h5py.File, population_name: str) -> int:
    return len(h5["edges"][population_name]["source_node_id"])


def list_of_node_properties_from_h5(h5: h5py.File, population_name: str) -> list[str]:
    return [_k for _k in h5["nodes"][population_name]["0"] if not _k.startswith("@")]


def list_of_edge_properties_from_h5(h5: h5py.File, population_name: str) -> list[str]:
    return list(h5["edges"][population_name].get("0", {}).keys())


def unique_node_property_values_from_h5(h5: h5py.File, population_name: str) -> dict[str, list]:
    vals_dict = {}
    grp = h5["nodes"][population_name]["0"]
    for k in grp.get("@library", {}):
        vals_dict[k] = grp["@library"][k][:]
    return vals_dict


def number_of_nodes_per_unique_value_from_h5(h5: h5py.File, population_name: str) -> dict:
    vals_dict = {}
    grp = h5["nodes"][population_name]["0"]
    for k in grp.get("@library", {}):
        prop_vals = grp["@library"][k][:]
        prop_idx_counts = pd.Series(grp[k][:]).value_counts()
        prop_idx_counts = prop_idx_counts.reindex(range(len(prop_vals)), fill_value=0)
        prop_idx_counts.index = pd.Index(prop_vals)
        vals_dict[k] = prop_idx_counts.to_dict()
    return vals_dict


def node_location_properties_from_h5(h5: h5py.File, population_name: str) -> dict:
    vals_dict = {}
    grp = h5["nodes"][population_name]["0"]
    coord_names = [
        _coord
        for _coord in [SpatialCoordinate.x, SpatialCoordinate.y, SpatialCoordinate.z]
        if str(_coord) in grp
    ]
    for _coord in coord_names:
        coord_v = grp[str(_coord)][:]
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


def edge_property_stats_from_h5(h5: h5py.File, population_name: str) -> dict:
    vals_dict = {}
    grp = h5["edges"][population_name]["0"]
    for edgeprop_name in grp:
        vals = grp[edgeprop_name][:]
        vals_dict[edgeprop_name] = {
            "mean": np.mean(vals),
            "median": np.median(vals),
            "min": np.min(vals),
            "max": np.max(vals),
            "std": np.std(vals),
        }
    return vals_dict


def degree_stats_from_h5(
    h5: h5py.File, population_name: str
) -> dict[DegreeTypes, dict[str, float]]:
    grp = h5["edges"][population_name]["indices"]

    def _degrees(_grp: h5py.Group) -> np.ndarray:
        range_to_len = np.diff(_grp["range_to_edge_id"], axis=1).transpose()[0]
        cc = np.hstack([0, np.cumsum(range_to_len)]).astype(int)
        deg = cc[_grp["node_id_to_ranges"][:, 1]] - cc[_grp["node_id_to_ranges"][:, 0]]
        return deg

    grp_in = grp["target_to_source"]
    indegs = _degrees(grp_in)
    if "source_to_target" in grp:
        grp_out = grp["source_to_target"]
        outdegs = _degrees(grp_out)
    else:
        outdegs = np.zeros_like(indegs)

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
    return stats


def properties_from_nodes_files(
    config_dict: dict,
    manifest: dict,
    temp_dir: str,
    db_client: Client,
    circuit_id: str,
    asset_id: str,
    level_of_detail_specs: dict,
) -> dict:
    default_lod = level_of_detail_specs[ALL_POPULATIONS]
    lst_req_props = [
        "population_length",
        "property_list",
        "property_unique_values",
        "property_value_counts",
    ]
    properties_dict = {}
    for nodefile, nodepop in get_names_of_typed_node_populations(
        config_dict, "virtual"
    ) + get_names_of_typed_node_populations(config_dict, "biophysical"):
        if level_of_detail_specs.get(nodepop, default_lod) > CircuitStatsLevelOfDetail.none:
            remote_path = _get_asset_path(nodefile, manifest, temp_dir)
            properties_dict[nodepop] = {_k: {} for _k in lst_req_props}
            with (
                TemporaryAsset(remote_path, db_client, circuit_id, asset_id) as fn,
                h5py.File(fn, "r") as h5,
            ):
                properties_dict[nodepop]["population_length"] = number_of_nodes_from_h5(h5, nodepop)
                properties_dict[nodepop]["property_list"] = list_of_node_properties_from_h5(
                    h5, nodepop
                )
                properties_dict[nodepop]["property_unique_values"] = (
                    unique_node_property_values_from_h5(h5, nodepop)
                )
                properties_dict[nodepop]["property_value_counts"] = (
                    number_of_nodes_per_unique_value_from_h5(h5, nodepop)
                )
                if (
                    level_of_detail_specs.get(nodepop, default_lod)
                    > CircuitStatsLevelOfDetail.basic
                ):
                    properties_dict[nodepop]["node_location_info"] = (
                        node_location_properties_from_h5(h5, nodepop)
                    )

    return properties_dict


def properties_from_edges_files(
    config_dict: str,
    manifest: dict,
    temp_dir: str,
    db_client: Client,
    circuit_id: str,
    asset_id: str,
    level_of_detail_specs: dict,
) -> dict:
    default_lod = level_of_detail_specs[ALL_POPULATIONS]
    lst_req_props = ["number_of_edges", "property_list", "property_stats", "degrees"]
    properties_dict = {}
    for edgefile, edgepop in get_names_of_typed_edge_populations(
        config_dict, "chemical"
    ) + get_names_of_typed_edge_populations(config_dict, "electrical"):
        if level_of_detail_specs.get(edgepop, default_lod) > CircuitStatsLevelOfDetail.none:
            properties_dict[edgepop] = {_k: {} for _k in lst_req_props}
            remote_path = _get_asset_path(edgefile, manifest, temp_dir)
            with (
                TemporaryAsset(remote_path, db_client, circuit_id, asset_id) as fn,
                h5py.File(fn, "r") as h5,
            ):
                properties_dict[edgepop]["number_of_edges"] = number_of_edges_from_h5(h5, edgepop)
                properties_dict[edgepop]["property_list"] = list_of_edge_properties_from_h5(
                    h5, edgepop
                )
                if (
                    level_of_detail_specs.get(edgepop, default_lod)
                    > CircuitStatsLevelOfDetail.basic
                ):
                    properties_dict[edgepop]["property_stats"] = edge_property_stats_from_h5(
                        h5, edgepop
                    )
                    properties_dict[edgepop]["degrees"] = degree_stats_from_h5(h5, edgepop)
    return properties_dict


class CircuitMetricsNodePopulation(BaseModel):
    number_of_nodes: int
    name: str
    population_type: NodePopulationType
    property_names: list[str]
    property_unique_values: dict[str, list[str]]
    property_value_counts: dict[str, dict[str, int]]
    node_location_info: dict[SpatialCoordinate, dict[str, float]] | None


class CircuitMetricsEdgePopulation(BaseModel):
    number_of_edges: int
    name: str
    population_type: EdgePopulationType
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

    def __iter__(self) -> Iterator[CircuitMetricsEdgePopulation | None]:
        """Provides iterator over all populations (node + edge)."""
        yield from self.biophysical_node_populations + self.virtual_node_populations

    def __getitem__(self, key: str) -> CircuitMetricsNodePopulation | CircuitMetricsEdgePopulation:
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
        entity_id=circuit_id,
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
    # Use db_client.download_file with temporary directory instead
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = Path(temp_dir) / "circuit_config.json"

        db_client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=temp_file_path,
            asset_path="circuit_config.json",
        )

        # Read the file and load JSON
        content = Path(temp_file_path).read_text(encoding="utf-8")
        config_dict = json.loads(content)
        manifest = {k: str(Path(temp_dir) / Path(v)) for k, v in config_dict["manifest"].items()}

    dict_props = properties_from_config(config_dict)
    nodesets = names_from_node_sets_file(
        config_dict, manifest, temp_dir, db_client, circuit_id, asset_id
    )

    node_props = properties_from_nodes_files(
        config_dict, manifest, temp_dir, db_client, circuit_id, asset_id, level_of_detail_nodes
    )
    edge_props = properties_from_edges_files(
        config_dict, manifest, temp_dir, db_client, circuit_id, asset_id, level_of_detail_edges
    )

    biophys_pops = []
    for _, nodepop in dict_props["names_of_biophys_node_populations"]:
        pop = None
        if nodepop in node_props:
            pop = CircuitMetricsNodePopulation(
                number_of_nodes=node_props[nodepop]["population_length"],
                name=nodepop,
                population_type=NodePopulationType.biophysical,
                property_names=node_props[nodepop]["property_list"],
                property_unique_values=node_props[nodepop]["property_unique_values"],
                property_value_counts=node_props[nodepop]["property_value_counts"],
                # Use .get() because node_location_info is only added when level_of_detail > basic
                node_location_info=node_props[nodepop].get("node_location_info"),
            )
        biophys_pops.append(pop)
    virtual_pops = []
    for _, nodepop in dict_props["names_of_virtual_node_populations"]:
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
    for _, edgepop in dict_props["names_of_chemical_edge_populations"]:
        pop = None
        if edgepop in edge_props:
            pop = CircuitMetricsEdgePopulation(
                number_of_edges=edge_props[edgepop]["number_of_edges"],
                name=edgepop,
                population_type=EdgePopulationType.chemical,
                property_names=edge_props[edgepop]["property_list"],
                property_stats=edge_props[edgepop]["property_stats"],
                degree_stats=edge_props[edgepop]["degrees"],
            )
        chemical_pops.append(pop)
    electrical_pops = []
    for _, edgepop in dict_props["names_of_electrical_edge_populations"]:
        pop = None
        if edgepop in edge_props:
            pop = CircuitMetricsEdgePopulation(
                number_of_edges=edge_props[edgepop]["number_of_edges"],
                name=edgepop,
                population_type=EdgePopulationType.electrical,
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
        names_of_biophys_node_populations=[
            _x[1] for _x in dict_props["names_of_biophys_node_populations"]
        ],
        names_of_virtual_node_populations=[
            _x[1] for _x in dict_props["names_of_virtual_node_populations"]
        ],
        names_of_chemical_edge_populations=[
            _x[1] for _x in dict_props["names_of_chemical_edge_populations"]
        ],
        names_of_electrical_edge_populations=[
            _x[1] for _x in dict_props["names_of_electrical_edge_populations"]
        ],
        names_of_nodesets=nodesets,
        biophysical_node_populations=biophys_pops,
        virtual_node_populations=virtual_pops,
        chemical_edge_populations=chemical_pops,
        electrical_edge_populations=electrical_pops,
    )
