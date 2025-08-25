import json
import h5py
import tempfile
import pandas
import os.path
from pathlib import Path
from typing import Any
from httpx import HTTPStatusError

from entitysdk.client import Client
from entitysdk.models.circuit import Circuit
from pydantic import BaseModel


def _get_asset_path(config_path: str,
                    manifest: dict,
                    temp_dir: str
) -> str:
    for k, v in manifest.items():
        config_path = config_path.replace(k, v)
    path_to_fetch = Path(config_path).relative_to(temp_dir)
    return path_to_fetch


class TemporaryAsset(object):
    def __init__(self, path_to_fetch, db_client, circuit_id, asset_id):
        self._remote_path = str(path_to_fetch)
        self._db_client = db_client
        self._circuit_id = circuit_id
        self._asset_id = asset_id
    
    def __enter__(self):
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
    
    def __exit__(self, *args):
        self.temp_dir.__exit__(*args)


def get_names_of_typed_node_populations(
        config_dict: dict,
        type_str: str
) -> int:
    names = []
    lst_nodes = config_dict.get("networks", {}).get("nodes", [])
    for nodefile in lst_nodes:
        for population_name, population in nodefile["populations"].items():
            if population["type"] == type_str:
                names.append((nodefile["nodes_file"],
                              population_name))
    return names

def get_number_of_typed_node_populations(
        config_dict: dict,
        type_str: str
) -> int:
    return len(get_names_of_typed_node_populations(config_dict, type_str))


def properties_from_config(config_dict):
    return {
        "number_of_biophys_node_populations": get_number_of_typed_node_populations(config_dict, "biophysical"),
        "number_of_virtual_node_populations": get_number_of_typed_node_populations(config_dict, "virtual")
    }

def number_of_nodes_from_h5(h5, population_name):
    return len(h5["nodes"][population_name]["node_type_id"])

def list_of_node_properties_from_h5(h5, population_name):
    return [_k for _k in
            h5["nodes"][population_name]["0"]
            if not _k.startswith("@")]

def unique_node_property_values_from_h5(h5, population_name):
    vals_dict = {}
    grp = h5["nodes"][population_name]["0"]
    for k in grp.get("@library", {}).keys():
        vals_dict[k] = grp["@library"][k][:]
    return vals_dict

def number_of_nodes_per_unique_value_from_h5(h5, population_name):
    vals_dict = {}
    grp = h5["nodes"][population_name]["0"]
    for k in grp.get("@library", {}).keys():
        prop_vals = grp["@library"][k][:]
        prop_idx_counts = pandas.Series(grp[k][:]).value_counts()
        prop_idx_counts = prop_idx_counts.reindex(range(len(prop_vals)), fill_value=0)
        prop_idx_counts.index = pandas.Index(prop_vals)
        vals_dict[k] = prop_idx_counts.to_dict()
    return vals_dict

def properties_from_nodes_files(config_dict, manifest, temp_dir,
                                db_client, circuit_id, asset_id):
    properties_dict = {}
    for nodefile, nodepop in get_names_of_typed_node_populations(config_dict, "virtual"):
        remote_path = _get_asset_path(nodefile, manifest, temp_dir)
        with TemporaryAsset(remote_path, db_client, circuit_id, asset_id) as fn:
            with h5py.File(fn, "r") as h5:
                properties_dict.setdefault("virtual_population_lengths", {})[nodepop] =\
                number_of_nodes_from_h5(h5, nodepop)
    
    for nodefile, nodepop in get_names_of_typed_node_populations(config_dict, "biophysical"):
        remote_path = _get_asset_path(nodefile, manifest, temp_dir)
        with TemporaryAsset(remote_path, db_client, circuit_id, asset_id) as fn:
            with h5py.File(fn, "r") as h5:
                properties_dict.setdefault("biophysical_population_lengths", {})[nodepop] =\
                number_of_nodes_from_h5(h5, nodepop)
                properties_dict.setdefault("biophysical_property_lists", {})[nodepop] =\
                list_of_node_properties_from_h5(h5, nodepop)
                properties_dict.setdefault("biophysical_property_unique_values", {})[nodepop] =\
                unique_node_property_values_from_h5(h5, nodepop)
                properties_dict.setdefault("biophysical_property_value_counts", {})[nodepop] =\
                number_of_nodes_per_unique_value_from_h5(h5, nodepop)
    return properties_dict


class CircuitMetricsOutput(BaseModel):
    config: dict[str, Any]
    number_of_biophys_node_populations: int
    number_of_virtual_node_populations: int
    virtual_population_lengths: dict[str, int]
    biophysical_population_lengths: dict[str, int]
    biophysical_property_lists: dict[str, list[str]]
    biophysical_property_unique_values: dict[str, dict[str, list[str]]]
    biophysical_property_value_counts: dict[str, dict[str, dict[str, int]]]



def get_circuit_metrics(
    circuit_id: str,
    db_client: Client,
) -> CircuitMetricsOutput:
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
        manifest = {
            k: str(Path(temp_dir) / Path(v))
            for k, v in config_dict["manifest"].items()
        }
    
    dict_props = properties_from_config(config_dict)
    dict_props.update(
        properties_from_nodes_files(config_dict, manifest, temp_dir,
                                    db_client, circuit_id, asset_id)
    )

    return CircuitMetricsOutput(config=config_dict, **dict_props)
