#!/bin/env python
# /// script
# dependencies = ['h5py', 'libsonata', 'numpy']
# ///
# the above allows one to run `uv run create_data.py` without a virtualenv
import itertools as it
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import h5py
import libsonata
import numpy as np


@dataclass
class SonataAttribute:
    name: str
    type: type
    prefix: bool


NODE_TYPES = [
    SonataAttribute("node_type_id", type=int, prefix=False),
    SonataAttribute("model_template", type=h5py.string_dtype(), prefix=True),
    SonataAttribute("model_type", type=h5py.string_dtype(), prefix=True),
]
NODE_TYPES = {attr.name: attr for attr in NODE_TYPES}

EDGE_TYPES = [
    SonataAttribute("edge_type_id", type=int, prefix=False),
    SonataAttribute("w", type=np.float32, prefix=True),
    SonataAttribute("model_template", type=h5py.string_dtype(), prefix=True),
]
EDGE_TYPES = {attr.name: attr for attr in EDGE_TYPES}


@dataclass
class Edges:
    src: str
    tgt: str
    type: str
    connections: list[tuple[int, int]]
    edge_pop: str | None = None
    synapses: list[int] | None = None


def _expand_values(attr, value, count):
    if isinstance(value, str):
        ds_value = [value] * count
    elif isinstance(value, Sequence):
        assert len(value) == count, f"For {attr}, {len(value)} != (count) {count}"
        ds_value = value
    elif isinstance(value, Iterable):
        ds_value = list(it.islice(value, count))
    else:
        ds_value = [value] * count

    return ds_value


def make_nodes(filename, name, count, wanted_attributes):
    with h5py.File(filename, "w") as h5:
        dg = h5.create_group(f"/nodes/{name}")

        for attr, value in wanted_attributes.items():
            typ = NODE_TYPES[attr]
            ds_name = ("0/" if typ.prefix else "") + typ.name
            ds_value = _expand_values(attr, value, count)
            dg.create_dataset(name=ds_name, data=ds_value, dtype=typ.type)

        # virtual population has no attribute
        # but group "0" is required by libsonata function open_population
        if "0" not in dg:
            dg.create_group("0")


def make_edges(filename, edges, wanted_attributes):
    name = f"{edges.src}__{edges.tgt}__{edges.type}"
    src_ids, tgt_ids = zip(*edges.connections, strict=True)
    count = len(src_ids)
    with h5py.File(filename, "w") as h5:
        dg = h5.create_group(f"/edges/{name}")

        for attr, value in wanted_attributes.items():
            typ = EDGE_TYPES[attr]
            ds_name = ("0/" if typ.prefix else "") + typ.name
            ds_value = _expand_values(attr, value, count)
            dg.create_dataset(name=ds_name, data=ds_value, dtype=typ.type)

        ds = dg.create_dataset("source_node_id", data=np.array(src_ids, dtype=int))
        ds.attrs["node_population"] = edges.src
        ds = dg.create_dataset("target_node_id", data=np.array(tgt_ids, dtype=int))
        ds.attrs["node_population"] = edges.tgt

        if edges.edge_pop and edges.synapses:
            ds = dg.create_dataset("0/synapse_id", data=np.array(edges.synapses, dtype=int))
            ds.attrs["edge_population"] = edges.edge_pop
            ds_value = _expand_values("synapse_population", edges.edge_pop, len(edges.synapses))
            ds = dg.create_dataset("0/synapse_population", data=ds_value, dtype=h5py.string_dtype())

    libsonata.EdgePopulation.write_indices(
        filename,
        name,
        source_node_count=max(src_ids) + 1,  # add 1 because IDs are 0-based
        target_node_count=max(tgt_ids) + 1,
    )


def make_drosophila_nodes():
    wanted = {
        "node_type_id": -1,
        "model_type": "brian2_point",
        "model_template": "json:drosophila",
    }
    make_nodes(filename="nodes.h5", name="drosophila", count=3, wanted_attributes=wanted)


def make_drosophila_edges():
    edges = Edges(
        "drosophila",
        "drosophila",
        "brian2_synapse",
        [(i, j) for i, j in it.product(range(3), range(3)) if i != j],
    )
    wanted_attributes = {
        "edge_type_id": -1,
        "model_template": "json:synapse",
        "w": 250,  # mv
    }
    make_edges(filename="edges.h5", edges=edges, wanted_attributes=wanted_attributes)


if __name__ == "__main__":
    make_drosophila_nodes()
    make_drosophila_edges()
    with Path("circuit_config.json").open("w", encoding="utf-8") as fd:
        json.dump(
            {
                "components": {"point_neuron_models_dir": "models"},
                "node_sets_file": "node_sets.json",
                "target_simulator": "Brian2",
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "nodes.h5",
                            "populations": {"drosophila": {"type": "brian2_point"}},
                        }
                    ],
                    "edges": [
                        {
                            "edges_file": "edges.h5",
                            "populations": {
                                "drosophila__drosophila__brian2_synapse": {"type": "brian2_synapse"}
                            },
                        }
                    ],
                },
            },
            fd,
        )

    with Path("node_sets.json").open("w", encoding="utf-8") as fd:
        json.dump(
            {
                "All": {"population": "drosophila"},
                "0": {"population": "drosophila", "node_id": [0]},
                # gustatory receptor neurons an untargeted Brian2 stimulus defaults to
                "sugar": {"population": "drosophila", "node_id": [0, 1]},
            },
            fd,
        )
