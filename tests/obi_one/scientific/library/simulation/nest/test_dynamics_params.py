"""Tests for the per-node and per-edge ``dynamics_params`` datasets of multisynapse models."""

from pathlib import Path

import h5py
import nest
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork
from obi_one.utils.io import write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    _write_edges,
    write_nest_circuit,
)

PORTS = {"E_rev": [0.0, -80.0], "tau_rise": [1.0, 1.0], "tau_decay": [2.0, 2.0]}


def write_port_circuit(
    root: Path, receptor_type: np.ndarray, node_dynamics: dict[str, np.ndarray] | None = None
) -> Path:
    """The test circuit with a two-port neuron model and edges that pick a port."""
    circuit = write_nest_circuit(root)
    templates = root / "model_templates"
    node_dynamics = node_dynamics or {}
    for name in ("iaf_psc_alpha_type1", "iaf_psc_alpha_type2"):
        template = {
            "model": "nest:aeif_cond_beta_multisynapse",
            "params": {} if node_dynamics else PORTS,
            "dynamics_params": dict.fromkeys(node_dynamics, "mV"),
        }
        write_json(template, templates / "exc" / f"{name}.json")
    with h5py.File(root / "network" / "exc_nodes.h5", "a") as handle:
        for key, values in node_dynamics.items():
            handle.create_dataset(f"nodes/exc/0/dynamics_params/{key}", data=values)
    write_json(
        {
            "model": "nest:static_synapse",
            "params": {"delay": 2.0, "weight": 50.0, "receptor_type": 1},
        },
        templates / "input__exc" / "static_synapse.json",
    )
    write_json(
        {
            "model": "nest:static_synapse",
            "params": {"weight": 1.0, "delay": 1.0},
            "dynamics_params": {"receptor_type": "1"},
        },
        templates / "exc__exc" / "tsodyks2_synapse.json",
    )
    _write_edges(
        root / "network" / "exc_exc_edges.h5",
        "exc__exc",
        ("exc", "exc"),
        ([0, 1, 2], [1, 2, 3]),
        "tsodyks2_synapse",
    )
    with h5py.File(root / "network" / "exc_exc_edges.h5", "a") as handle:
        handle.create_dataset("edges/exc__exc/0/dynamics_params/receptor_type", data=receptor_type)
    return circuit.simulation_config


def test_an_integer_receptor_type_selects_the_port_of_each_edge(tmp_path):
    config = write_port_circuit(tmp_path, np.array([1, 2, 1], dtype=np.int64))
    network = NestSonataNetwork(config)
    collections = network.BuildNetwork()
    connections = nest.GetConnections(source=collections["exc"], synapse_model="static_synapse")
    by_source = dict(zip(connections.get("source"), connections.get("receptor"), strict=True))
    first = collections["exc"].tolist()[0]
    assert [by_source[first + i] for i in range(3)] == [1, 2, 1]


def test_list_parameters_in_the_template_apply_to_every_node(tmp_path):
    config = write_port_circuit(tmp_path, np.array([1, 2, 1], dtype=np.int64))
    nodes = NestSonataNetwork(config).BuildNetwork()["exc"]
    for e_rev in nodes.get("E_rev"):
        assert list(e_rev) == PORTS["E_rev"]


def test_a_receptor_type_that_is_not_an_integer_is_an_error(tmp_path):
    config = write_port_circuit(tmp_path, np.array([1.0, 1.5, 1.0], dtype=np.float32))
    with pytest.raises(ValueError, match="receptor_type must hold integers"):
        NestSonataNetwork(config).BuildNetwork()


def test_a_list_valued_edge_dataset_is_an_error_that_points_to_the_template(tmp_path):
    config = write_port_circuit(tmp_path, np.ones((3, 2), dtype=np.int64))
    with pytest.raises(ValueError, match=r"'exc__exc'.*1-D.*'params' of the template"):
        NestSonataNetwork(config).BuildNetwork()


def test_a_list_valued_node_dataset_is_an_error_that_points_to_the_template(tmp_path):
    config = write_port_circuit(
        tmp_path,
        np.array([1, 2, 1], dtype=np.int64),
        node_dynamics={"E_rev": np.tile([0.0, -80.0], (4, 1))},
    )
    with pytest.raises(ValueError, match=r"'exc'.*E_rev.*1-D.*'params' of the template"):
        NestSonataNetwork(config).BuildNetwork()
