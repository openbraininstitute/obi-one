"""Write a Brian2 point-neuron SONATA circuit from resolved EM connectivity.

The format mirrors the Drosophila FlyWire Brian2 SONATA circuit in ``examples/J_drosophila``
(a ``brian2_point`` node population, ``brian2_synapse`` edge populations and JSON neuron / synapse
model templates under ``models/``). The modelled neurons form the point-neuron population; the
external presynaptic partners form a ``virtual`` population. The neuronal and synaptic parameters
are borrowed from the Drosophila brain model as placeholders. A fraction
(``INHIBITORY_FRACTION``) of neurons are made inhibitory, encoded as in that model: a negative
weight on their outgoing synapses, plus an ``EXC``/``INH`` ``synapse_class`` node property.
"""

import json
import logging
from pathlib import Path

import h5py
import libsonata
import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
from voxcell import CellCollection

from obi_one.scientific.tasks.point_neuron_circuit_from_em.connectivity import (
    EdgeSet,
    ResolvedConnectivity,
)

L = logging.getLogger(__name__)

POINT_POPULATION = "point_neurons"
VIRTUAL_POPULATION = "virtual_afferent_neurons"
NEURON_MODEL = "point_neuron"
VIRTUAL_MODEL = "virtual_neuron"
SYNAPSE_MODEL = "synapse"

# Per-synapse weight (mV). Placeholder borrowed from the Drosophila brain model ``w_syn``.
W_SYN_MV = 0.275

# Fraction of neurons made inhibitory; their outgoing synapses get negative weights (as in the
# Drosophila model, where inhibition is encoded as a negative edge weight). The assignment is
# deterministic (seeded) so a given circuit is reproducible.
INHIBITORY_FRACTION = 0.2
_INHIBITORY_SEED = 0

_NODES_FILE = "nodes.h5"
_EDGES_FILE = "edges.h5"
_MODELS_DIR = "models"
_NODE_SETS_FILE = "node_sets.json"
_CONFIG_FILE = "circuit_config.json"

# Placeholder leaky integrate-and-fire point-neuron parameters, borrowed verbatim from
# examples/J_drosophila/output-630/models/drosophila.json.
NEURON_MODEL_PARAMS = {
    "params": {
        "model": [
            "",
            "dv/dt = (v_0 - v + g) / t_mbr : volt (unless refractory)",
            "dg/dt = -g / tau               : volt (unless refractory) ",
            "rfc                            : second",
            "",
        ],
        "method": "linear",
        "threshold": "v > v_th",
        "reset": "v = v_rst; w = 0; g = 0 * mV",
        "refractory": "rfc",
    },
    "namespace": {
        "t_mbr": [20.0, "ms"],
        "tau": [5.0, "ms"],
        "v_0": [-52.0, "mV"],
        "v_th": [-45.0, "mV"],
        "v_rst": [-52.0, "mV"],
    },
    "initial": {
        "v": [-52.0, "mV"],
        "g": [0, "mV"],
        "rfc": [2.2, "ms"],
    },
}

# Placeholder synapse parameters, borrowed from the Drosophila model (output-630/models).
SYNAPSE_MODEL_PARAMS = {
    "params": {
        "model": "w : volt",
        "on_pre": "g += w",
        "delay": [1.8, "ms"],
    },
    "dynamics": {
        "w": "mV",
    },
}

# Placeholder model template for the external (virtual) spike-source neurons. Virtual nodes are
# not simulated by the point-neuron backend; this exists so the virtual population has its own
# model_template (as required by the SONATA virtual-node schema).
VIRTUAL_MODEL_PARAMS = {
    "params": {},
    "namespace": {},
    "initial": {},
}


def _write_models(output_dir: Path) -> None:
    models_dir = output_dir / _MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / f"{NEURON_MODEL}.json").write_text(json.dumps(NEURON_MODEL_PARAMS, indent=2))
    (models_dir / f"{VIRTUAL_MODEL}.json").write_text(json.dumps(VIRTUAL_MODEL_PARAMS, indent=2))
    (models_dir / f"{SYNAPSE_MODEL}.json").write_text(json.dumps(SYNAPSE_MODEL_PARAMS, indent=2))


def _inhibitory_mask(n_neurons: int) -> numpy.ndarray:
    """Mark ~``INHIBITORY_FRACTION`` of neurons as inhibitory (deterministic, seeded)."""
    mask = numpy.zeros(n_neurons, dtype=bool)
    n_inhibitory = round(INHIBITORY_FRACTION * n_neurons)
    if n_inhibitory:
        rng = numpy.random.default_rng(_INHIBITORY_SEED)
        mask[rng.choice(n_neurons, size=n_inhibitory, replace=False)] = True
    return mask


def _node_dataframe(
    pt_root_ids: list[int],
    model_type: str,
    model_template: str,
    inhibitory_mask: numpy.ndarray,
) -> pandas.DataFrame:
    return pandas.DataFrame(
        index=numpy.arange(len(pt_root_ids)),
        data={
            "model_type": model_type,
            "model_template": model_template,
            "synapse_class": numpy.where(inhibitory_mask, "INH", "EXC"),
            "pt_root_id": numpy.asarray(pt_root_ids, dtype=numpy.int64),
        },
    )


def _write_nodes(
    output_dir: Path,
    point_pt_root_ids: list[int],
    virtual_pt_root_ids: list[int],
    point_inhibitory: numpy.ndarray,
    virtual_inhibitory: numpy.ndarray,
) -> None:
    nodes_path = output_dir / _NODES_FILE
    point = CellCollection.from_dataframe(
        _node_dataframe(
            point_pt_root_ids, "brian2_point", f"json:{NEURON_MODEL}", point_inhibitory
        ),
        index_offset=0,
    )
    point.population_name = POINT_POPULATION
    point.save_sonata(nodes_path, mode="w")

    if virtual_pt_root_ids:
        # Virtual nodes are external spike sources; they get their own placeholder model template,
        # which also satisfies the SONATA virtual-node schema's model_template requirement.
        virtual = CellCollection.from_dataframe(
            _node_dataframe(
                virtual_pt_root_ids, "virtual", f"json:{VIRTUAL_MODEL}", virtual_inhibitory
            ),
            index_offset=0,
        )
        virtual.population_name = VIRTUAL_POPULATION
        virtual.save_sonata(nodes_path, mode="a")


def _write_edge_population(
    h5: h5py.File,
    name: str,
    edges: EdgeSet,
    source_population: str,
    target_population: str,
    source_inhibitory: numpy.ndarray,
) -> None:
    n_edges = len(edges.source_node_id)
    group = h5.create_group(f"edges/{name}")
    source = group.create_dataset("source_node_id", data=edges.source_node_id.astype(numpy.uint32))
    source.attrs["node_population"] = source_population
    target = group.create_dataset("target_node_id", data=edges.target_node_id.astype(numpy.uint32))
    target.attrs["node_population"] = target_population
    group.create_dataset("edge_type_id", data=numpy.full(n_edges, -1, dtype=numpy.int8))

    # Synapses from inhibitory presynaptic neurons get a negative weight (Drosophila convention).
    sign = numpy.where(source_inhibitory[edges.source_node_id], -1.0, 1.0)
    weights = edges.synapse_count.astype(numpy.float64) * W_SYN_MV * sign  # mV

    group0 = group.create_group("0")
    group0.create_dataset("w", data=weights)
    group0.create_dataset("@library/model_template", data=[f"json:{SYNAPSE_MODEL}"])
    group0.create_dataset("model_template", data=numpy.zeros(n_edges, dtype=numpy.uint8))


def _write_edges(
    output_dir: Path,
    connectivity: ResolvedConnectivity,
    point_inhibitory: numpy.ndarray,
    virtual_inhibitory: numpy.ndarray,
) -> list[str]:
    edges_path = output_dir / _EDGES_FILE
    n_point = len(connectivity.point_pt_root_ids)
    n_virtual = len(connectivity.virtual_pt_root_ids)
    internal_name = f"{POINT_POPULATION}__{POINT_POPULATION}__brian2_synapse"
    external_name = f"{VIRTUAL_POPULATION}__{POINT_POPULATION}__brian2_synapse"

    to_index = []
    with h5py.File(edges_path, "w") as h5:
        if len(connectivity.internal_edges.source_node_id):
            _write_edge_population(
                h5, internal_name, connectivity.internal_edges,
                POINT_POPULATION, POINT_POPULATION, point_inhibitory,
            )
            to_index.append((internal_name, n_point, n_point))
        if len(connectivity.external_edges.source_node_id):
            _write_edge_population(
                h5, external_name, connectivity.external_edges,
                VIRTUAL_POPULATION, POINT_POPULATION, virtual_inhibitory,
            )
            to_index.append((external_name, n_virtual, n_point))

    for name, n_src, n_tgt in to_index:
        libsonata.EdgePopulation.write_indices(str(edges_path), name, n_src, n_tgt)
    return [name for name, _n_src, _n_tgt in to_index]


def _write_node_sets(output_dir: Path) -> None:
    path = output_dir / _NODE_SETS_FILE
    node_sets = {
        "All": {"population": POINT_POPULATION},
        "EXC": {"synapse_class": "EXC"},
        "INH": {"synapse_class": "INH"},
    }
    path.write_text(json.dumps(node_sets, indent=2))


def _write_config(
    output_dir: Path, edge_population_names: list[str], *, has_virtual: bool
) -> Path:
    node_populations = {POINT_POPULATION: {"type": "brian2_point"}}
    if has_virtual:
        node_populations[VIRTUAL_POPULATION] = {"type": "virtual"}

    config = {
        "components": {"point_neuron_models_dir": _MODELS_DIR},
        "node_sets_file": _NODE_SETS_FILE,
        "target_simulator": "Brian2",
        "networks": {
            "nodes": [{"nodes_file": _NODES_FILE, "populations": node_populations}],
            "edges": [
                {
                    "edges_file": _EDGES_FILE,
                    "populations": {
                        name: {"type": "brian2_synapse"} for name in edge_population_names
                    },
                }
            ],
        },
    }
    path = output_dir / _CONFIG_FILE
    path.write_text(json.dumps(config, indent=2))
    return path


def write_brian2_sonata_circuit(output_dir: Path, connectivity: ResolvedConnectivity) -> Path:
    """Write a Brian2 point-neuron SONATA circuit from resolved EM connectivity.

    Args:
        output_dir: directory the circuit is written to (created if needed).
        connectivity: the resolved connectivity (modelled + virtual neurons and edges).

    Returns:
        Path to the written ``circuit_config.json``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    point_inhibitory = _inhibitory_mask(len(connectivity.point_pt_root_ids))
    virtual_inhibitory = _inhibitory_mask(len(connectivity.virtual_pt_root_ids))

    _write_models(output_dir)
    _write_nodes(
        output_dir,
        connectivity.point_pt_root_ids,
        connectivity.virtual_pt_root_ids,
        point_inhibitory,
        virtual_inhibitory,
    )
    edge_population_names = _write_edges(
        output_dir, connectivity, point_inhibitory, virtual_inhibitory
    )
    _write_node_sets(output_dir)
    return _write_config(
        output_dir, edge_population_names, has_virtual=bool(connectivity.virtual_pt_root_ids)
    )
