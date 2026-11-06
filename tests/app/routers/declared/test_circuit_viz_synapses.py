import json
from http import HTTPStatus
from unittest.mock import MagicMock
from uuid import uuid4

import h5py
import libsonata
import numpy as np
import pytest
from fastapi import HTTPException

from app.services.circuit_visualization import get_afferent_synapses

_POPULATION = "test__test__chemical"
_SURFACE_X = [1.0, 2.0, 3.0]
_SURFACE_Y = [10.0, 20.0, 30.0]
_SURFACE_Z = [100.0, 200.0, 300.0]
_SECTION_IDS = [0, 7, 12]
_TARGET_NODES = [0, 0, 1]


def _write_edges(path, *, with_surface: bool) -> None:
    """A minimal SONATA edge file — the datasets libsonata needs, and nothing else."""
    with h5py.File(path, "w") as f:
        population = f.create_group(f"edges/{_POPULATION}")
        count = len(_SECTION_IDS)
        population.create_dataset("source_node_id", data=np.zeros(count, dtype=np.uint64))
        population.create_dataset("target_node_id", data=np.array(_TARGET_NODES, dtype=np.uint64))
        population.create_dataset("edge_type_id", data=np.full(count, -1, dtype=np.int64))
        population["source_node_id"].attrs["node_population"] = "nodes"
        population["target_node_id"].attrs["node_population"] = "nodes"

        group = population.create_group("0")
        group.create_dataset("delay", data=np.ones(count, dtype=np.float32))
        if with_surface:
            group.create_dataset("afferent_surface_x", data=np.array(_SURFACE_X, dtype=np.float32))
            group.create_dataset("afferent_surface_y", data=np.array(_SURFACE_Y, dtype=np.float32))
            group.create_dataset("afferent_surface_z", data=np.array(_SURFACE_Z, dtype=np.float32))
            group.create_dataset(
                "afferent_section_id", data=np.array(_SECTION_IDS, dtype=np.uint32)
            )

        population.create_group("indices")


def _write_nodes(path) -> None:
    with h5py.File(path, "w") as f:
        population = f.create_group("nodes/nodes")
        population.create_dataset("node_type_id", data=np.full(2, -1, dtype=np.int64))
        group = population.create_group("0")
        group.create_dataset("x", data=np.zeros(2, dtype=np.float32))


@pytest.fixture
def client():
    """A client whose download is a no-op — the fixture has already written the files."""
    return MagicMock()


def _read(config, tmp_path, client):
    return get_afferent_synapses(config, tmp_path, client, uuid4(), uuid4())


@pytest.fixture
def circuit(tmp_path):
    def _build(*, with_surface: bool) -> libsonata.CircuitConfig:
        _write_nodes(tmp_path / "nodes.h5")
        _write_edges(tmp_path / "edges.h5", with_surface=with_surface)
        config = {
            "version": 2,
            "networks": {
                # Declared virtual so libsonata does not demand the morphology and mechanism
                # directories a biophysical population needs. Nothing here reads a morphology —
                # the synapse positions are stored on the edges.
                "nodes": [
                    {"nodes_file": "nodes.h5", "populations": {"nodes": {"type": "virtual"}}}
                ],
                "edges": [{"edges_file": "edges.h5", "populations": {_POPULATION: {}}}],
            },
        }
        path = tmp_path / "circuit_config.json"
        path.write_text(json.dumps(config))
        return libsonata.CircuitConfig.from_file(str(path))

    return _build


def test_afferent_synapses_are_flattened_in_file_order(circuit, tmp_path, client):
    """The three coordinate arrays are interleaved per synapse, in file order.

    The viewer uploads this straight to the GPU as one buffer, so a stride or ordering slip
    would scatter every synapse somewhere plausible-looking but wrong.
    """
    [group] = _read(circuit(with_surface=True), tmp_path, client)

    assert group.population_name == _POPULATION
    assert group.coordinates == [
        1.0, 10.0, 100.0,
        2.0, 20.0, 200.0,
        3.0, 30.0, 300.0,
    ]  # fmt: skip
    # Aligned with the positions: a client projects index i of one using index i of the others,
    # so a shuffle would attach a synapse to the wrong branch of the wrong cell.
    assert group.section_ids == _SECTION_IDS
    assert group.target_node_ids == _TARGET_NODES


def test_an_escaping_edge_path_is_refused(circuit, tmp_path, client):
    """The edge path comes from the circuit's own config, and is used as a download target.

    Left unchecked, a `..` would write outside the working directory.
    """
    config = circuit(with_surface=True)
    (tmp_path / "edges.h5").unlink()
    escaping = tmp_path / "nested" / "circuit_config.json"

    with pytest.raises(HTTPException) as raised:
        get_afferent_synapses(config, escaping.parent, client, uuid4(), uuid4())

    assert raised.value.status_code == HTTPStatus.BAD_REQUEST


def test_a_population_without_surface_positions_is_skipped(circuit, tmp_path, client):
    """A connectome can record connectivity without geometry, and that is not an error.

    Returning nothing lets the viewer draw the morphology alone rather than failing the request
    over synapses it never had.
    """
    assert _read(circuit(with_surface=False), tmp_path, client) == []


def test_a_missing_edge_file_is_fetched(circuit, tmp_path, client):
    """The config names its edge files, but the asset only hands them over one at a time.

    Downloading the config alone leaves nothing to read, and the population-level skip would
    then quietly report a circuit with no synapses instead of failing.
    """
    config = circuit(with_surface=True)
    (tmp_path / "edges.h5").unlink()

    _read(config, tmp_path, client)

    [call] = client.download_file.call_args_list
    assert call.kwargs["asset_path"].name == "edges.h5"


def test_an_undownloadable_edge_file_is_skipped(circuit, tmp_path, client):
    """A circuit whose edges cannot be fetched still draws its morphology."""
    config = circuit(with_surface=True)
    (tmp_path / "edges.h5").unlink()
    client.download_file.side_effect = RuntimeError("gone")

    assert _read(config, tmp_path, client) == []
