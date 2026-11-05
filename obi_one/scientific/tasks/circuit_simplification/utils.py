"""Helpers for the outputs of circuit simplification."""

import csv
import json
from pathlib import Path

import h5py
import libsonata

NEST_SIMULATION_CONFIG_NAME = "simulation_config.json"


def node_population(dataset: h5py.Dataset) -> str:
    """The node population a SONATA ``source_node_id``/``target_node_id`` dataset refers to."""
    name = dataset.attrs["node_population"]
    return name.decode() if isinstance(name, bytes) else str(name)


def resolve_manifest_path(path: str, manifest: dict[str, str], base_dir: Path) -> Path:
    """A circuit config path with its manifest variables (e.g. ``$BASE_DIR``) substituted."""
    for variable, value in manifest.items():
        path = path.replace(variable, value)
    return (base_dir / path).resolve()


def declare_nest_node_populations(
    entries: list[dict], manifest: dict[str, str], base_dir: Path
) -> dict[str, int]:
    """Declare the populations of NEST node entries in place; return each population's size.

    A population takes the ``model_type`` of its node types file. Populations without an
    attribute group get an empty one, since libsonata cannot open them otherwise.

    Raises:
        ValueError: If a node types file names more than one model type.
    """
    population_sizes: dict[str, int] = {}
    for entry in entries:
        types_path = resolve_manifest_path(entry["node_types_file"], manifest, base_dir)
        with types_path.open(encoding="utf-8", newline="") as f:
            model_types = {row["model_type"] for row in csv.DictReader(f, delimiter=" ")}
        if len(model_types) != 1:
            msg = f"{types_path} names {len(model_types)} model types: {sorted(model_types)}"
            raise ValueError(msg)
        model_type = model_types.pop()
        with h5py.File(resolve_manifest_path(entry["nodes_file"], manifest, base_dir), "a") as f:
            sizes = {name: len(group["node_type_id"]) for name, group in f["nodes"].items()}
            for group in f["nodes"].values():
                group.require_group("0")
        population_sizes.update(sizes)
        entry["populations"] = {name: {"type": model_type} for name in sizes}
    return population_sizes


def declare_nest_edge_populations(
    entries: list[dict],
    manifest: dict[str, str],
    base_dir: Path,
    population_sizes: dict[str, int],
) -> None:
    """Declare the populations of NEST edge entries in place, and write missing edge indices."""
    for entry in entries:
        edges_path = resolve_manifest_path(entry["edges_file"], manifest, base_dir)
        with h5py.File(edges_path, "r") as f:
            endpoints = {
                name: (
                    node_population(group["source_node_id"]),
                    node_population(group["target_node_id"]),
                )
                for name, group in f["edges"].items()
                if "indices" not in group
            }
            names = list(f["edges"])
        for name, (source, target) in endpoints.items():
            libsonata.EdgePopulation.write_indices(
                str(edges_path),
                name,
                source_node_count=population_sizes[source],
                target_node_count=population_sizes[target],
            )
        entry["populations"] = {name: {"type": "chemical"} for name in names}


def make_nest_export_loadable(export_dir: Path) -> None:
    """Turn a sonata-simplify NEST export into a SONATA circuit that libsonata can load.

    The exporter writes its circuit config for NEST's loader: it sets
    ``"target_simulator": "NEST"``, which libsonata (and with it bluepysnap and the platform)
    rejects, names no populations, and writes virtual populations without an attribute group and
    edge files without indices. This declares each node population with the ``model_type`` of
    its node types file and each edge population as ``chemical``, adds the missing attribute
    groups and edge indices, and moves ``target_simulator`` and ``run`` into a
    ``simulation_config.json`` next to the circuit config. NEST still loads the export, with
    ``nest.SonataNetwork(circuit_config, sim_config=simulation_config)``, and the sonata-simplify
    NEST runner reads the circuit config as before.

    Raises:
        ValueError: If the circuit config is not a NEST export's, or a node types file names
            more than one model type.
        FileExistsError: If the export already has a simulation config.
    """
    circuit_config_path = export_dir / "circuit_config.json"
    config = json.loads(circuit_config_path.read_text(encoding="utf-8"))
    if config.get("target_simulator") != "NEST":
        msg = f"{circuit_config_path} is not a NEST export: its target_simulator is not 'NEST'."
        raise ValueError(msg)
    simulation_config_path = export_dir / NEST_SIMULATION_CONFIG_NAME
    if simulation_config_path.exists():
        msg = f"{simulation_config_path} already exists."
        raise FileExistsError(msg)

    manifest = config.get("manifest", {})
    population_sizes = declare_nest_node_populations(
        config["networks"]["nodes"], manifest, export_dir
    )
    declare_nest_edge_populations(
        config["networks"]["edges"], manifest, export_dir, population_sizes
    )

    simulation_config = {
        # nest.SonataNetwork parses the manifest of every config it is given.
        "manifest": {"$BASE_DIR": "."},
        "target_simulator": config.pop("target_simulator"),
        "network": circuit_config_path.name,
        "run": config.pop("run"),
    }
    circuit_config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    simulation_config_path.write_text(json.dumps(simulation_config, indent=2), encoding="utf-8")
