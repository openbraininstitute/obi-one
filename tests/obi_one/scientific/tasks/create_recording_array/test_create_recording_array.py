"""Tests for create_recording_array/create_recording_array.py."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import matplotlib.pyplot as plt
import pytest

import obi_one as obi
import obi_one.scientific.tasks.create_recording_array.create_recording_array as test_module
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuron.schemas import NeurodamusMechanismBuild
from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
    CreateExtracellularRecordingArrayTask,
)
from obi_one.types import SimulationBackend

from tests.utils import CIRCUIT_DIR

_MODULE = "obi_one.scientific.tasks.create_recording_array.create_recording_array"
_CIRCUIT_PATH = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
_PLACED = {
    "origin_x": 3900.0,
    "origin_y": -1600.0,
    "origin_z": -2400.0,
    "rotation_x": 15.0,
    "rotation_z": 30.0,
}


@pytest.fixture
def mock_db_client():
    client = Mock()
    entity = SimpleNamespace(id=uuid4())
    client.register_entity.return_value = entity
    return client


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy")
    return path


def _mechanism_build(tmp_path):
    return NeurodamusMechanismBuild(
        libnrnmech_path=_touch(tmp_path / "libnrnmech.so"),
        libcorenrnmech_path=_touch(tmp_path / "libcorenrnmech.so"),
        special_binary_path=_touch(tmp_path / "special"),
    )


def _make_task(tmp_path, *, circuit_path=_CIRCUIT_PATH):
    config = Mock()
    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "coord"
    config.initialize.circuit = Mock()
    config.initialize.calculation_method = "PointSource"
    config.electrode_locations = {
        "probe": obi.LinearExtracellularLocations(n_electrodes=2, spacing=20.0, **_PLACED),
    }
    return CreateExtracellularRecordingArrayTask.model_construct(config=config), circuit_path


def _resolved_circuit(circuit_path):
    circuit = Circuit(name="tiny", path=str(circuit_path))
    return circuit, SimpleNamespace(id=uuid4())


def test_write_electrode_json_writes_correct_format(tmp_path):
    pytest.importorskip("bluerecording")

    block = SimpleNamespace(
        get_global_electrode_xyz_locations=lambda: [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    )
    output_path = tmp_path / "electrodes.json"

    result = test_module._write_electrode_json({"probe_a": block}, "PointSource", output_path)

    assert result == output_path
    data = json.loads(output_path.read_text())
    assert len(data) == 2
    assert data[0]["name"] == "probe_a_electrode_0"
    assert data[0]["x"] == pytest.approx(1.0)
    assert data[0]["y"] == pytest.approx(2.0)
    assert data[0]["z"] == pytest.approx(3.0)
    assert data[0]["type"] == "PointSource"
    assert data[1]["name"] == "probe_a_electrode_1"


def test_write_electrode_json_multiple_blocks(tmp_path):
    pytest.importorskip("bluerecording")

    block_a = SimpleNamespace(get_global_electrode_xyz_locations=lambda: [(0.0, 0.0, 0.0)])
    block_b = SimpleNamespace(get_global_electrode_xyz_locations=lambda: [(10.0, 10.0, 10.0)])
    output_path = tmp_path / "electrodes.json"

    test_module._write_electrode_json({"A": block_a, "B": block_b}, "LineSource", output_path)

    data = json.loads(output_path.read_text())
    assert len(data) == 2
    assert data[0]["name"] == "A_electrode_0"
    assert data[1]["name"] == "B_electrode_0"
    assert data[1]["type"] == "LineSource"


def test_plot_electrode_array_saves_plot(tmp_path):
    sonata_circuit = Circuit(name="tiny", path=str(_CIRCUIT_PATH)).sonata_circuit
    electrode_locations = {
        "Lin": obi.LinearExtracellularLocations(n_electrodes=2, spacing=20.0, **_PLACED),
    }
    image_path = tmp_path / "plots" / "electrode_array.png"
    mock_figure = MagicMock()

    with patch(f"{_MODULE}.plot_extracellular_arrays", return_value=mock_figure):
        test_module._plot_electrode_array(sonata_circuit, electrode_locations, image_path)

    mock_figure.savefig.assert_called_once_with(image_path, dpi=150, bbox_inches="tight")
    plt.close("all")


def test_create_and_cleanup_temp_dir(tmp_path):
    task, _ = _make_task(tmp_path)

    temp_path = task._create_temp_dir()
    assert temp_path.exists()
    assert task._temp_dir is not None

    task._cleanup_temp_dir()
    assert task._temp_dir is None


def test_create_temp_dir_cleans_up_previous(tmp_path):
    task, _ = _make_task(tmp_path)

    first_path = task._create_temp_dir()
    second_path = task._create_temp_dir()

    assert first_path != second_path
    assert second_path.exists()
    task._cleanup_temp_dir()


def test_execute_compiles_mechanisms_when_mod_dir_exists(tmp_path, mock_db_client):
    task, circuit_path = _make_task(tmp_path)
    circuit, circuit_entity = _resolved_circuit(circuit_path)
    mechanism_build = _mechanism_build(tmp_path)
    electrode_json = tmp_path / "coord" / "electrodes.json"
    weights_path = tmp_path / "coord" / "weights.h5"

    with (
        patch.object(
            CreateExtracellularRecordingArrayTask,
            "_get_execution_activity",
            return_value=None,
        ),
        patch.object(CreateExtracellularRecordingArrayTask, "_update_execution_activity"),
        patch(f"{_MODULE}.db_sdk.resolve_circuit", return_value=(circuit, circuit_entity)),
        patch(f"{_MODULE}._plot_electrode_array"),
        patch(f"{_MODULE}.compile_mechanisms", return_value=mechanism_build) as mock_compile,
        patch(f"{_MODULE}._write_electrode_json", return_value=electrode_json),
        patch(f"{_MODULE}.run_bluerecording_write_weights", return_value=weights_path),
    ):
        task.execute(db_client=mock_db_client)

    mock_compile.assert_called_once_with(
        output_dir=tmp_path / "coord" / "compiled_mods",
        mechanisms_dirs=[circuit_path.parent / "mod"],
        simulation_backend=SimulationBackend.neurodamus,
    )
    mock_db_client.register_entity.assert_called_once()
    assert mock_db_client.upload_file.call_count == 2


def test_execute_compiles_from_config_mechanisms_dir_without_local_mod(tmp_path, mock_db_client):
    circuit_config_path = tmp_path / "circuit" / "circuit_config.json"
    circuit_config_path.parent.mkdir()
    circuit_config_path.write_text("{}")
    mechanisms_dir = tmp_path / "external_mods"
    mechanisms_dir.mkdir()

    task, _ = _make_task(tmp_path, circuit_path=circuit_config_path)
    circuit = SimpleNamespace(
        name="config_mods",
        path=str(circuit_config_path),
        sonata_circuit=MagicMock(),
    )
    circuit_entity = SimpleNamespace(id=uuid4())
    mechanism_build = _mechanism_build(tmp_path)

    mock_pop_props = MagicMock()
    mock_pop_props.mechanisms_dir = str(mechanisms_dir)
    mock_circuit_config = MagicMock()
    mock_circuit_config.node_populations = ["bio"]
    mock_circuit_config.node_population_properties.return_value = mock_pop_props

    with (
        patch.object(
            CreateExtracellularRecordingArrayTask,
            "_get_execution_activity",
            return_value=None,
        ),
        patch.object(CreateExtracellularRecordingArrayTask, "_update_execution_activity"),
        patch(f"{_MODULE}.db_sdk.resolve_circuit", return_value=(circuit, circuit_entity)),
        patch(f"{_MODULE}.libsonata.CircuitConfig.from_file", return_value=mock_circuit_config),
        patch(f"{_MODULE}._plot_electrode_array"),
        patch(f"{_MODULE}.compile_mechanisms", return_value=mechanism_build) as mock_compile,
        patch(f"{_MODULE}._write_electrode_json", return_value=tmp_path / "coord" / "e.json"),
        patch(
            f"{_MODULE}.run_bluerecording_write_weights",
            return_value=tmp_path / "coord" / "weights.h5",
        ),
    ):
        task.execute(db_client=mock_db_client)

    mock_compile.assert_called_once_with(
        output_dir=tmp_path / "coord" / "compiled_mods",
        mechanisms_dirs=[mechanisms_dir],
        simulation_backend=SimulationBackend.neurodamus,
    )


def test_execute_uses_neocortex_fallback_without_mods(tmp_path, mock_db_client):
    circuit_dir = tmp_path / "circuit"
    circuit_dir.mkdir()
    circuit_config_path = circuit_dir / "circuit_config.json"
    circuit_config_path.write_text(
        json.dumps(
            {
                "components": {},
                "networks": {"nodes": [], "edges": []},
                "version": 2.3,
                "manifest": {"$BASE_DIR": "./"},
            }
        )
    )

    task, _ = _make_task(tmp_path, circuit_path=circuit_config_path)
    circuit = SimpleNamespace(
        name="empty",
        path=str(circuit_config_path),
        sonata_circuit=MagicMock(),
    )
    circuit_entity = SimpleNamespace(id=uuid4())
    electrode_json = tmp_path / "coord" / "electrodes.json"
    weights_path = tmp_path / "coord" / "weights.h5"

    with (
        patch.object(
            CreateExtracellularRecordingArrayTask,
            "_get_execution_activity",
            return_value=None,
        ),
        patch.object(CreateExtracellularRecordingArrayTask, "_update_execution_activity"),
        patch(f"{_MODULE}.db_sdk.resolve_circuit", return_value=(circuit, circuit_entity)),
        patch(f"{_MODULE}._plot_electrode_array"),
        patch(f"{_MODULE}.compile_mechanisms") as mock_compile,
        patch(f"{_MODULE}._write_electrode_json", return_value=electrode_json),
        patch(
            f"{_MODULE}.run_bluerecording_write_weights",
            return_value=weights_path,
        ) as mock_bluerecording,
    ):
        task.execute(db_client=mock_db_client)

    mock_compile.assert_not_called()
    mock_bluerecording.assert_called_once()
    assert (
        mock_bluerecording.call_args.kwargs["nrnmech_lib_path"]
        == Path("/opt/obi/neocortex/x86_64/libnrnmech.so").absolute()
    )
