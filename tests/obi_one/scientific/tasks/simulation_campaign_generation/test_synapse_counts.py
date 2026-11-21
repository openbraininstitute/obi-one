"""The synapses that generation records next to the neuron count of a simulation.

Generation stages the nodes of the circuit only. The synapses come from the indices of the edge
files, read remotely with ``Client.open_remote_file``.
"""

import io
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from entitysdk.models import Simulation

from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library import circuit_synapses
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    FakeDBClient,
    build_config,
    generate,
)
from tests.utils import CIRCUIT_DIR

ENTITYSDK_FIELDS = dict(Simulation.model_fields)
N_CELLS = 10
N_SYNAPSES = 471 + 260 + 176


@dataclass
class RemoteDBClient(FakeDBClient):
    """Serves the files of the full circuit as remote files, as entitycore and S3 would."""

    circuit_dir: Path | None = None
    entity: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(id=uuid4()))
    asset: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(id=uuid4()))
    opened: list[str] = field(default_factory=list)
    block_sizes: list[int] = field(default_factory=list)
    fail_with: Exception | None = None

    def select_assets(self, _entity, _selection):
        return SimpleNamespace(one=lambda: self.asset)

    def list_directory(self, **_):
        files = {
            p.relative_to(self.circuit_dir): SimpleNamespace(size=p.stat().st_size)
            for p in self.circuit_dir.rglob("*")
            if p.is_file()
        }
        return SimpleNamespace(files=files)

    def open_remote_file(self, *, asset_path, size, block_size, **_):
        if self.fail_with is not None:
            raise self.fail_with
        self.opened.append(asset_path)
        self.block_sizes.append(block_size)
        content = (self.circuit_dir / asset_path).read_bytes()
        assert len(content) == size
        return io.BytesIO(content)


@pytest.fixture
def full_circuit(tmp_path):
    directory = tmp_path / "full"
    shutil.copytree(CIRCUIT_DIR / "N_10__top_nodes_dim6", directory)
    return directory / "circuit_config.json"


@pytest.fixture
def db_client(full_circuit, tmp_path, monkeypatch):
    """A client for a circuit from entitycore, staged with its nodes only."""
    monkeypatch.setattr(circuit_synapses, "SYNAPSES_PER_CELL_CACHE", {})
    staged = tmp_path / "staged"
    shutil.copytree(full_circuit.parent, staged)
    for edges_file in staged.rglob("edges.h5"):
        edges_file.unlink()
    client = RemoteDBClient(circuit_dir=full_circuit.parent)
    staged_circuit = Circuit(name="staged", path=str(staged / "circuit_config.json"))
    monkeypatch.setattr(CircuitFromID, "entity", lambda _self, _client: client.entity)
    monkeypatch.setattr(CircuitFromID, "stage_circuit", lambda _self, **_: staged_circuit)
    fields = dict(ENTITYSDK_FIELDS)
    fields["number_synapses"] = fields["number_neurons"]
    monkeypatch.setattr(Simulation, "model_fields", fields)
    return client


def config():
    return build_config(CircuitSimulationSingleConfig, circuit=CircuitFromID(id_str=str(uuid4())))


def recorded(db_client):
    (update,) = db_client.calls_to("update_entity")
    return update.kwargs["attrs_or_entity"]


def test_the_synapses_onto_the_simulated_cells_are_recorded(db_client, tmp_path):
    generate(config(), tmp_path / "out", db_client=db_client)

    assert recorded(db_client) == {"number_neurons": N_CELLS, "number_synapses": N_SYNAPSES}


def test_only_the_edges_files_are_opened_remotely(db_client, tmp_path):
    generate(config(), tmp_path / "out", db_client=db_client)

    assert sorted(db_client.opened) == [
        "POm__S1nonbarrel_neurons__chemical/edges.h5",
        "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/edges.h5",
        "VPM__S1nonbarrel_neurons__chemical/edges.h5",
    ]


def test_the_indices_are_read_in_small_blocks(db_client, tmp_path):
    """An index is about 100 kB, and the time of a request does not depend on its size."""
    generate(config(), tmp_path / "out", db_client=db_client)

    assert db_client.block_sizes == [256 * 1024] * 3


def test_a_circuit_is_read_once_for_all_its_simulations(db_client, tmp_path):
    for i in range(2):
        generate(config(), tmp_path / "out", db_client=db_client, subdirectory=str(i))

    assert len(db_client.opened) == 3
    assert [
        u.kwargs["attrs_or_entity"]["number_synapses"] for u in db_client.calls_to("update_entity")
    ] == [N_SYNAPSES] * 2


@pytest.mark.parametrize(
    "error", [OSError("Expected 206 for a range request, got 200"), KeyError("indices")]
)
def test_a_circuit_that_cannot_be_read_records_the_neurons_only(db_client, tmp_path, caplog, error):
    db_client.fail_with = error

    with caplog.at_level(logging.WARNING):
        generate(config(), tmp_path / "out", db_client=db_client)

    assert recorded(db_client) == {"number_neurons": N_CELLS}
    assert "are not counted" in caplog.text


def test_another_circuit_is_read_again(db_client, tmp_path):
    generate(config(), tmp_path / "out", db_client=db_client, subdirectory="0")
    db_client.asset = SimpleNamespace(id=uuid4())

    generate(config(), tmp_path / "out", db_client=db_client, subdirectory="1")

    assert len(db_client.opened) == 6


def test_a_failed_read_is_tried_again_by_the_next_simulation(db_client, tmp_path):
    db_client.fail_with = OSError("Expected 206 for a range request, got 200")
    generate(config(), tmp_path / "out", db_client=db_client, subdirectory="0")
    db_client.fail_with = None

    generate(config(), tmp_path / "out", db_client=db_client, subdirectory="1")

    updates = db_client.calls_to("update_entity")
    assert [u.kwargs["attrs_or_entity"].get("number_synapses") for u in updates] == [
        None,
        N_SYNAPSES,
    ]


def test_staged_edges_are_read_from_disk(db_client, full_circuit, tmp_path, monkeypatch):
    staged_circuit = Circuit(name="full", path=str(full_circuit))
    monkeypatch.setattr(CircuitFromID, "stage_circuit", lambda _self, **_: staged_circuit)

    generate(config(), tmp_path / "out", db_client=db_client)

    assert db_client.opened == []
    assert recorded(db_client)["number_synapses"] == N_SYNAPSES


def test_an_entitysdk_without_the_field_records_the_neurons_only(db_client, tmp_path, monkeypatch):
    monkeypatch.setattr(Simulation, "model_fields", ENTITYSDK_FIELDS)

    generate(config(), tmp_path / "out", db_client=db_client)

    assert recorded(db_client) == {"number_neurons": N_CELLS}
    assert db_client.opened == []


def test_a_local_circuit_records_the_neurons_only(db_client, full_circuit, tmp_path):
    local = build_config(
        CircuitSimulationSingleConfig, circuit=Circuit(name="local", path=str(full_circuit))
    )

    generate(local, tmp_path / "out", db_client=db_client)

    assert recorded(db_client) == {"number_neurons": N_CELLS}
