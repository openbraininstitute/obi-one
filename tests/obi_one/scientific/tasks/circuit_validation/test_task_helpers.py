"""Unit tests for circuit validation task helpers — additional coverage."""

import json
import subprocess  # noqa: S404
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import pytest

from obi_one.scientific.tasks.circuit_validation.task import (
    _compile_mechanisms,
    _find_mod_dir,
    _get_population_sizes,
    _update_h5_dataset,
    _validate_emodel_paths,
    _validate_id_mapping_files,
    _validate_morphology_paths,
)

# ---------------------------------------------------------------------------
# _find_mod_dir
# ---------------------------------------------------------------------------


class TestFindModDir:
    def test_returns_mechanisms_dir(self, tmp_path):
        mod_dir = tmp_path / "mechanisms"
        mod_dir.mkdir()
        config_path = tmp_path / "circuit_config.json"
        cfg = {
            "manifest": {"$BASE_DIR": str(tmp_path)},
            "components": {"mechanisms_dir": str(mod_dir)},
            "networks": {"nodes": [], "edges": []},
        }
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _find_mod_dir(config_path)
        assert result == mod_dir

    def test_returns_none_when_no_mechanisms_dir(self, tmp_path):
        config_path = tmp_path / "circuit_config.json"
        cfg = {
            "manifest": {"$BASE_DIR": str(tmp_path)},
            "components": {},
            "networks": {"nodes": [], "edges": []},
        }
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _find_mod_dir(config_path)
        assert result is None


# ---------------------------------------------------------------------------
# _compile_mechanisms
# ---------------------------------------------------------------------------


class TestCompileMechanisms:
    def test_success(self, tmp_path):
        mod_dir = tmp_path / "mods"
        mod_dir.mkdir()
        (mod_dir / "NaTg.mod").write_text("NEURON { SUFFIX NaTg }\n")

        with patch("obi_one.scientific.tasks.circuit_validation.task.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            _compile_mechanisms(mod_dir, tmp_path)

        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "nrnivmodl" in args[0][0][0]
        assert str(mod_dir) in args[0][0]

    def test_failure_raises(self, tmp_path):
        mod_dir = tmp_path / "mods"
        mod_dir.mkdir()

        with patch("obi_one.scientific.tasks.circuit_validation.task.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "nrnivmodl", stderr=b"syntax error in PROCEDURE"
            )
            with pytest.raises(RuntimeError, match="MOD compilation failed"):
                _compile_mechanisms(mod_dir, tmp_path)


# ---------------------------------------------------------------------------
# _get_population_sizes
# ---------------------------------------------------------------------------


class TestGetPopulationSizes:
    def test_reads_sizes(self, tmp_path):
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            f.create_group("nodes/pop_a")
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(42, dtype=np.int32))
            f.create_group("nodes/pop_b")
            f["nodes/pop_b"].create_dataset("node_type_id", data=np.zeros(10, dtype=np.int32))

        cfg = {"networks": {"nodes": [{"nodes_file": str(nodes_file), "populations": {}}]}}
        result = _get_population_sizes(cfg)
        assert result == {"pop_a": 42, "pop_b": 10}

    def test_handles_missing_file(self):
        cfg = {"networks": {"nodes": [{"nodes_file": "/nonexistent/nodes.h5"}]}}
        result = _get_population_sizes(cfg)
        assert result == {}

    def test_empty_config(self):
        assert _get_population_sizes({}) == {}
        assert _get_population_sizes({"networks": {}}) == {}
        assert _get_population_sizes({"networks": {"nodes": []}}) == {}


# ---------------------------------------------------------------------------
# _validate_morphology_paths
# ---------------------------------------------------------------------------


class TestValidateMorphologyPaths:
    def test_valid_morphology_dir(self, tmp_path):
        morph_dir = tmp_path / "morphologies"
        morph_dir.mkdir()

        cfg = {
            "components": {"morphologies_dir": str(morph_dir)},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_morphology_paths(config_path)
        assert errors == []

    def test_missing_morphology_dir(self, tmp_path):
        cfg = {
            "components": {"morphologies_dir": str(tmp_path / "nonexistent")},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_morphology_paths(config_path)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_skips_virtual_populations(self, tmp_path):
        cfg = {
            "components": {"morphologies_dir": "/nonexistent"},
            "networks": {"nodes": [{"populations": {"virt": {"type": "virtual"}}}]},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_morphology_paths(config_path)
        assert errors == []

    def test_skips_alternate_morphologies(self, tmp_path):
        cfg = {
            "components": {"morphologies_dir": "/nonexistent"},
            "networks": {
                "nodes": [
                    {
                        "populations": {
                            "pop_a": {
                                "type": "biophysical",
                                "alternate_morphologies": {"h5v1": "/path"},
                            }
                        }
                    }
                ]
            },
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_morphology_paths(config_path)
        assert errors == []

    def test_morphology_path_is_file_not_dir(self, tmp_path):
        morph_file = tmp_path / "morphologies"
        morph_file.write_text("I am a file")

        cfg = {
            "components": {"morphologies_dir": str(morph_file)},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_morphology_paths(config_path)
        assert len(errors) == 1
        assert "not a directory" in errors[0]


# ---------------------------------------------------------------------------
# _validate_emodel_paths
# ---------------------------------------------------------------------------


class TestValidateEmodelPaths:
    def test_valid_hoc_files_exist(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "CellA.hoc").write_text("begintemplate CellA\nendtemplate CellA\n")

        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:CellA"])

        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ]
            },
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_emodel_paths(config_path)
        assert errors == []

    def test_missing_hoc_file(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        # CellA.hoc does NOT exist

        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:CellA"])

        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ]
            },
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_emodel_paths(config_path)
        assert len(errors) == 1
        assert "CellA.hoc" in errors[0]
        assert "not found" in errors[0]

    def test_missing_hoc_dir(self, tmp_path):
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:CellA"])

        cfg = {
            "components": {"biophysical_neuron_models_dir": str(tmp_path / "nonexistent")},
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ]
            },
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_emodel_paths(config_path)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_skips_virtual_populations(self, tmp_path):
        cfg = {
            "components": {"biophysical_neuron_models_dir": "/nonexistent"},
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "x.h5",
                        "populations": {"virt": {"type": "virtual"}},
                    }
                ]
            },
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_emodel_paths(config_path)
        assert errors == []

    def test_relative_hoc_dir(self, tmp_path):
        hoc_dir = tmp_path / "relative_hoc"
        hoc_dir.mkdir()
        (hoc_dir / "MyCell.hoc").write_text("template")

        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:MyCell"])

        cfg = {
            "components": {"biophysical_neuron_models_dir": "relative_hoc"},
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ]
            },
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            errors = _validate_emodel_paths(config_path)
        assert errors == []


# ---------------------------------------------------------------------------
# _validate_id_mapping_files
# ---------------------------------------------------------------------------


class TestValidateIdMappingFiles:
    def test_no_id_mapping(self, tmp_path):
        cfg = {"components": {}, "networks": {"nodes": []}}
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _validate_id_mapping_files(config_path)
        assert result == []

    def test_missing_id_mapping_file(self, tmp_path):
        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": []},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _validate_id_mapping_files(config_path)
        assert result == []  # file doesn't exist => nothing to validate

    def test_stale_mapping_non_symlink(self, tmp_path):
        # Create id_mapping with stale new_ids
        id_mapping = tmp_path / "id_mapping.json"
        id_mapping.write_text(json.dumps({"pop_a": {"new_id": [0, 99]}}))

        # Create nodes file with only 10 nodes
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            f.create_group("nodes/pop_a")
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(10, dtype=np.int32))

        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": [{"nodes_file": str(nodes_file), "populations": {}}]},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _validate_id_mapping_files(config_path)
        assert len(result) == 1
        assert "stale" in result[0]
        assert id_mapping.exists()  # non-symlink file should NOT be removed

    def test_valid_mapping(self, tmp_path):
        id_mapping = tmp_path / "id_mapping.json"
        id_mapping.write_text(json.dumps({"pop_a": {"new_id": [0, 5, 9]}}))

        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            f.create_group("nodes/pop_a")
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(100, dtype=np.int32))

        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": [{"nodes_file": str(nodes_file), "populations": {}}]},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _validate_id_mapping_files(config_path)
        assert result == []


# ---------------------------------------------------------------------------
# _update_h5_dataset
# ---------------------------------------------------------------------------


class TestUpdateH5Dataset:
    def test_creates_new_dataset(self, tmp_path):
        h5_file = tmp_path / "test.h5"
        with h5py.File(h5_file, "w") as f:
            grp = f.create_group("dyn")
            _update_h5_dataset(grp, "holding_current", {0: 1.5, 3: 2.5}, 5, np)

        with h5py.File(h5_file, "r") as f:
            ds = f["dyn/holding_current"]
            assert ds[0] == pytest.approx(1.5)
            assert ds[1] == pytest.approx(0.0)
            assert ds[3] == pytest.approx(2.5)
            assert ds.shape[0] == 5

    def test_updates_existing_dataset(self, tmp_path):
        h5_file = tmp_path / "test.h5"
        with h5py.File(h5_file, "w") as f:
            grp = f.create_group("dyn")
            grp.create_dataset(
                "holding_current", data=np.array([10, 20, 30, 40, 50], dtype=np.float32)
            )

        with h5py.File(h5_file, "r+") as f:
            grp = f["dyn"]
            _update_h5_dataset(grp, "holding_current", {1: 99.0, 4: 88.0}, 5, np)

        with h5py.File(h5_file, "r") as f:
            ds = f["dyn/holding_current"]
            assert ds[0] == pytest.approx(10.0)
            assert ds[1] == pytest.approx(99.0)
            assert ds[4] == pytest.approx(88.0)


# ---------------------------------------------------------------------------
# run_circuit_validation — integration with mocks
# ---------------------------------------------------------------------------


class TestRunCircuitValidation:
    """Test the main validation flow with mocked external dependencies."""

    def _make_minimal_circuit(self, tmp_path):
        """Create a minimal staged circuit with config + nodes + edges."""
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        # morphologies dir
        morph_dir = circuit_dir / "morphologies"
        morph_dir.mkdir()

        # hoc dir
        hoc_dir = circuit_dir / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "CellA.hoc").write_text("begintemplate CellA\nendtemplate CellA\n")

        # nodes
        nodes_file = circuit_dir / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:CellA"])
            grp.create_dataset("morphology", data=[b"morph1"])
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(1, dtype=np.int32))

        # edges
        edges_file = circuit_dir / "edges.h5"
        with h5py.File(edges_file, "w") as f:
            pop = f.create_group("edges/pop_a__pop_a__chemical")
            pop.create_dataset("source_node_id", data=np.array([0], dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.array([0], dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(1, dtype=np.int32))

        config = {
            "manifest": {"$BASE_DIR": str(circuit_dir)},
            "components": {
                "morphologies_dir": str(morph_dir),
                "biophysical_neuron_models_dir": str(hoc_dir),
            },
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ],
                "edges": [
                    {
                        "edges_file": str(edges_file),
                        "populations": {"pop_a__pop_a__chemical": {}},
                    }
                ],
            },
        }
        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps(config))
        return config_path, circuit_dir

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_passes_with_no_errors(
        self,
        mock_libsonata_cfg,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # noqa: PLC0415

        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            run_circuit_validation,
        )

        config_path, _circuit_dir = self._make_minimal_circuit(tmp_path)

        # Setup mocks
        mock_stage.return_value = config_path

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_cfg_obj.node_populations = ["pop_a"]
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []  # no errors
        mock_hoc_loading.return_value = []  # no errors

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=False,
        )

        assert result["valid"] is True
        assert result["errors"] == []
        mock_update_status.assert_called_once_with(db_client, circuit_id, "active")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_fails_with_missing_morphology_dir(
        self,
        mock_libsonata_cfg,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # noqa: PLC0415

        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            run_circuit_validation,
        )

        config_path, _circuit_dir = self._make_minimal_circuit(tmp_path)

        # Point morphologies_dir to non-existent path
        cfg = json.loads(config_path.read_text())
        cfg["components"]["morphologies_dir"] = str(tmp_path / "nonexistent_morphologies")
        config_path.write_text(json.dumps(cfg))

        mock_stage.return_value = config_path

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []
        mock_hoc_loading.return_value = []

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=False,
        )

        assert result["valid"] is False
        assert any("does not exist" in e for e in result["errors"])
        mock_update_status.assert_called_once_with(db_client, circuit_id, "disqualified")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._compile_mechanisms")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_mod_compilation_failure(
        self,
        mock_libsonata_cfg,
        mock_snap_validate,  # noqa: ARG002
        mock_compile,
        mock_update_status,
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # noqa: PLC0415

        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            run_circuit_validation,
        )

        config_path, circuit_dir = self._make_minimal_circuit(tmp_path)

        # Add a mechanisms_dir with a .mod file
        mod_dir = circuit_dir / "mechanisms"
        mod_dir.mkdir()
        (mod_dir / "NaTg.mod").write_text("NEURON { SUFFIX NaTg }\n")

        cfg = json.loads(config_path.read_text())
        cfg["components"]["mechanisms_dir"] = str(mod_dir)
        config_path.write_text(json.dumps(cfg))

        mock_stage.return_value = config_path

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_compile.side_effect = RuntimeError("nrnivmodl failed: syntax error")

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=False,
        )

        assert result["valid"] is False
        assert any("nrnivmodl" in e for e in result["errors"])
        mock_update_status.assert_called_once_with(db_client, circuit_id, "disqualified")


# ---------------------------------------------------------------------------
# _validate_hoc_loading
# ---------------------------------------------------------------------------


class TestValidateHocLoading:
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_morphology_for_template")
    def test_no_hoc_files_returns_empty(self, mock_find_morph, mock_cfg, tmp_path):  # noqa: ARG002
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _validate_hoc_loading,
        )

        config_path = tmp_path / "circuit_config.json"
        config_path.write_text("{}")

        m = MagicMock()
        m.expanded_json = json.dumps({"components": {}, "networks": {"nodes": []}})
        mock_cfg.return_value = m

        result = _validate_hoc_loading(config_path, tmp_path, load_mods=False)
        assert result == []

    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_morphology_for_template")
    def test_hoc_no_morphology_skipped(self, mock_find_morph, mock_cfg, tmp_path):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _validate_hoc_loading,
        )

        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "Cell.hoc").write_text("begintemplate Cell\nendtemplate Cell\n")

        config_path = tmp_path / "circuit_config.json"
        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        config_path.write_text(json.dumps(cfg))

        m = MagicMock()
        m.expanded_json = json.dumps(cfg)
        mock_cfg.return_value = m
        mock_find_morph.return_value = None  # no morphology found

        result = _validate_hoc_loading(config_path, tmp_path, load_mods=False)
        assert result == []  # skipped, no error

    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_morphology_for_template")
    @patch("obi_one.scientific.validations.emodels.bluecellulab_initializable")
    def test_hoc_instantiation_failure(self, mock_init, mock_find_morph, mock_cfg, tmp_path):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _validate_hoc_loading,
        )

        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "BadCell.hoc").write_text("begintemplate BadCell\nendtemplate BadCell\n")

        morph_path = tmp_path / "morph.swc"
        morph_path.write_text("fake morph")

        config_path = tmp_path / "circuit_config.json"
        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        config_path.write_text(json.dumps(cfg))

        m = MagicMock()
        m.expanded_json = json.dumps(cfg)
        mock_cfg.return_value = m
        mock_find_morph.return_value = morph_path
        mock_init.side_effect = RuntimeError("NEURON crash")

        result = _validate_hoc_loading(config_path, tmp_path, load_mods=False)

        assert len(result) == 1
        assert "BadCell.hoc" in result[0]
        assert "failed to instantiate" in result[0]

    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_morphology_for_template")
    @patch("obi_one.scientific.validations.emodels.bluecellulab_initializable")
    def test_hoc_success(self, mock_init, mock_find_morph, mock_cfg, tmp_path):  # noqa: ARG002
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _validate_hoc_loading,
        )

        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "GoodCell.hoc").write_text("begintemplate GoodCell\nendtemplate GoodCell\n")

        morph_path = tmp_path / "morph.swc"
        morph_path.write_text("fake morph")

        config_path = tmp_path / "circuit_config.json"
        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        config_path.write_text(json.dumps(cfg))

        m = MagicMock()
        m.expanded_json = json.dumps(cfg)
        mock_cfg.return_value = m
        mock_find_morph.return_value = morph_path

        result = _validate_hoc_loading(config_path, tmp_path, load_mods=False)
        assert result == []


# ---------------------------------------------------------------------------
# _check_content_subset_of_parent
# ---------------------------------------------------------------------------


class TestCheckContentSubsetOfParent:
    @patch("bluepysnap.Circuit")
    def test_child_is_subset(self, mock_circuit_cls):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_content_subset_of_parent,
        )

        parent = MagicMock()
        child = MagicMock()

        # Parent has morphs {A, B, C} and templates {hoc:X, hoc:Y}
        parent_pop = MagicMock()
        parent_pop.property_names = ["morphology", "model_template"]
        parent_pop.get.side_effect = lambda properties: (
            MagicMock(to_list=lambda: ["A", "B", "C"])
            if properties == "morphology"
            else MagicMock(to_list=lambda: ["hoc:X", "hoc:Y"])
        )
        parent.nodes.population_names = ["pop_a"]
        parent.nodes.__getitem__ = lambda _self, _k: parent_pop

        # Child has morphs {A, B} and templates {hoc:X}
        child_pop = MagicMock()
        child_pop.property_names = ["morphology", "model_template"]
        child_pop.get.side_effect = lambda properties: (
            MagicMock(to_list=lambda: ["A", "B"])
            if properties == "morphology"
            else MagicMock(to_list=lambda: ["hoc:X"])
        )
        child.nodes.population_names = ["pop_a"]
        child.nodes.__getitem__ = lambda _self, _k: child_pop

        mock_circuit_cls.side_effect = [parent, child]

        from pathlib import Path  # noqa: PLC0415

        errors = _check_content_subset_of_parent(Path("child.json"), Path("parent.json"))
        assert errors == []

    @patch("bluepysnap.Circuit")
    def test_child_has_extra_morphologies(self, mock_circuit_cls):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_content_subset_of_parent,
        )

        parent = MagicMock()
        child = MagicMock()

        parent_pop = MagicMock()
        parent_pop.property_names = ["morphology", "model_template"]
        parent_pop.get.side_effect = lambda properties: (
            MagicMock(to_list=lambda: ["A"])
            if properties == "morphology"
            else MagicMock(to_list=lambda: ["hoc:X"])
        )
        parent.nodes.population_names = ["pop_a"]
        parent.nodes.__getitem__ = lambda _self, _k: parent_pop

        child_pop = MagicMock()
        child_pop.property_names = ["morphology", "model_template"]
        child_pop.get.side_effect = lambda properties: (
            MagicMock(to_list=lambda: ["A", "B", "NEW_MORPH"])
            if properties == "morphology"
            else MagicMock(to_list=lambda: ["hoc:X"])
        )
        child.nodes.population_names = ["pop_a"]
        child.nodes.__getitem__ = lambda _self, _k: child_pop

        mock_circuit_cls.side_effect = [parent, child]

        from pathlib import Path  # noqa: PLC0415

        errors = _check_content_subset_of_parent(Path("child.json"), Path("parent.json"))
        assert len(errors) == 1
        assert "morphology" in errors[0]

    @patch("bluepysnap.Circuit")
    def test_load_failure_returns_empty(self, mock_circuit_cls):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_content_subset_of_parent,
        )

        mock_circuit_cls.side_effect = RuntimeError("cannot load")

        from pathlib import Path  # noqa: PLC0415

        errors = _check_content_subset_of_parent(Path("child.json"), Path("parent.json"))
        assert errors == []


# ---------------------------------------------------------------------------
# _check_node_columns_unchanged
# ---------------------------------------------------------------------------


class TestCheckNodeColumnsUnchanged:
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_no_common_populations(self, mock_cfg):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_node_columns_unchanged,
        )

        child_cfg = MagicMock()
        child_cfg.node_populations = ["pop_new"]
        parent_cfg = MagicMock()
        parent_cfg.node_populations = ["pop_a"]
        mock_cfg.side_effect = [child_cfg, parent_cfg]

        from pathlib import Path  # noqa: PLC0415

        warnings = _check_node_columns_unchanged(Path("child.json"), Path("parent.json"))
        assert warnings == []

    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_attribute_names_differ(self, mock_cfg):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_node_columns_unchanged,
        )

        child_pop = MagicMock()
        child_pop.attribute_names = ["morphology", "mtype", "new_attr"]
        parent_pop = MagicMock()
        parent_pop.attribute_names = ["morphology", "mtype"]

        child_cfg = MagicMock()
        child_cfg.node_populations = ["pop_a"]
        child_cfg.node_population.return_value = child_pop
        parent_cfg = MagicMock()
        parent_cfg.node_populations = ["pop_a"]
        parent_cfg.node_population.return_value = parent_pop
        mock_cfg.side_effect = [child_cfg, parent_cfg]

        from pathlib import Path  # noqa: PLC0415

        warnings = _check_node_columns_unchanged(Path("child.json"), Path("parent.json"))
        assert len(warnings) == 1
        assert "attribute names differ" in warnings[0]

    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_attribute_values_changed(self, mock_cfg):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_node_columns_unchanged,
        )

        child_pop = MagicMock()
        child_pop.attribute_names = ["morphology", "mtype", "model_template"]
        child_pop.select_all.return_value = "all"
        child_pop.get_attribute.side_effect = lambda attr, _sel: (
            np.array(["m1", "m2"]) if attr == "morphology" else np.array(["L2", "CHANGED"])
        )

        parent_pop = MagicMock()
        parent_pop.attribute_names = ["morphology", "mtype", "model_template"]
        parent_pop.select_all.return_value = "all"
        parent_pop.get_attribute.side_effect = lambda attr, _sel: (
            np.array(["m1", "m2"]) if attr == "morphology" else np.array(["L2", "L5"])
        )

        child_cfg = MagicMock()
        child_cfg.node_populations = ["pop_a"]
        child_cfg.node_population.return_value = child_pop
        parent_cfg = MagicMock()
        parent_cfg.node_populations = ["pop_a"]
        parent_cfg.node_population.return_value = parent_pop
        mock_cfg.side_effect = [child_cfg, parent_cfg]

        from pathlib import Path  # noqa: PLC0415

        warnings = _check_node_columns_unchanged(Path("child.json"), Path("parent.json"))
        # mtype changed (not in allowed_changes) → warning
        assert len(warnings) == 1
        assert "mtype" in warnings[0]

    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_only_allowed_changes_no_warning(self, mock_cfg):
        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            _check_node_columns_unchanged,
        )

        child_pop = MagicMock()
        child_pop.attribute_names = ["morphology", "model_template", "etype"]
        child_pop.select_all.return_value = "all"
        # Only morphology is checked (model_template and etype are in allowed_changes)
        child_pop.get_attribute.return_value = np.array(["m1", "m2"])

        parent_pop = MagicMock()
        parent_pop.attribute_names = ["morphology", "model_template", "etype"]
        parent_pop.select_all.return_value = "all"
        parent_pop.get_attribute.return_value = np.array(["m1", "m2"])  # same values

        child_cfg = MagicMock()
        child_cfg.node_populations = ["pop_a"]
        child_cfg.node_population.return_value = child_pop
        parent_cfg = MagicMock()
        parent_cfg.node_populations = ["pop_a"]
        parent_cfg.node_population.return_value = parent_pop
        mock_cfg.side_effect = [child_cfg, parent_cfg]

        from pathlib import Path  # noqa: PLC0415

        warnings = _check_node_columns_unchanged(Path("child.json"), Path("parent.json"))
        assert warnings == []


# ---------------------------------------------------------------------------
# run_circuit_validation — subset checks branch
# ---------------------------------------------------------------------------


class TestRunCircuitValidationSubsetChecks:
    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task._check_content_subset_of_parent")
    @patch(
        "obi_one.scientific.tasks.circuit_validation.task._check_new_populations_not_biophysical"
    )
    @patch("obi_one.scientific.tasks.circuit_validation.task._check_node_columns_unchanged")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_subset_checks_invoked_for_customization(
        self,
        mock_libsonata_cfg,
        mock_node_cols,
        mock_new_pops,
        mock_content_subset,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,  # noqa: ARG002
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # noqa: PLC0415

        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            run_circuit_validation,
        )

        config_path = tmp_path / "circuit_config.json"
        morph_dir = tmp_path / "morphologies"
        morph_dir.mkdir()
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "Cell.hoc").write_text("x")
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:Cell"])
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(1, dtype=np.int32))
        cfg = {
            "components": {
                "morphologies_dir": str(morph_dir),
                "biophysical_neuron_models_dir": str(hoc_dir),
            },
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ]
            },
        }
        config_path.write_text(json.dumps(cfg))

        # mock stage to return our config for both child and parent
        mock_stage.return_value = config_path

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []
        mock_hoc_loading.return_value = []
        mock_new_pops.return_value = []
        mock_content_subset.return_value = []
        mock_node_cols.return_value = ["Population 'pop_a': attribute 'x' was modified"]

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = uuid4()  # has a parent → customization
        parent = MagicMock()
        db_client.get_entity.side_effect = [circuit, parent]

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=True,
        )

        assert result["valid"] is True
        assert len(result["warnings"]) == 1
        mock_new_pops.assert_called_once()
        mock_content_subset.assert_called_once()
        mock_node_cols.assert_called_once()

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task._check_content_subset_of_parent")
    @patch(
        "obi_one.scientific.tasks.circuit_validation.task._check_new_populations_not_biophysical"
    )
    @patch("obi_one.scientific.tasks.circuit_validation.task._check_node_columns_unchanged")
    @patch("obi_one.scientific.tasks.circuit_validation.task._recompute_dynamic_params")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    def test_recompute_dynamic_params_called(
        self,
        mock_libsonata_cfg,
        mock_recompute,
        mock_node_cols,
        mock_new_pops,
        mock_content_subset,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,  # noqa: ARG002
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # noqa: PLC0415

        from obi_one.scientific.tasks.circuit_validation.task import (  # noqa: PLC0415
            run_circuit_validation,
        )

        config_path = tmp_path / "circuit_config.json"
        morph_dir = tmp_path / "morphologies"
        morph_dir.mkdir()
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "Cell.hoc").write_text("x")
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:Cell"])
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(1, dtype=np.int32))
        cfg = {
            "components": {
                "morphologies_dir": str(morph_dir),
                "biophysical_neuron_models_dir": str(hoc_dir),
            },
            "networks": {
                "nodes": [
                    {
                        "nodes_file": str(nodes_file),
                        "populations": {"pop_a": {"type": "biophysical"}},
                    }
                ]
            },
        }
        config_path.write_text(json.dumps(cfg))

        mock_stage.return_value = config_path

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []
        mock_hoc_loading.return_value = []
        mock_new_pops.return_value = []
        mock_content_subset.return_value = []
        mock_node_cols.return_value = []

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = uuid4()
        parent = MagicMock()
        db_client.get_entity.side_effect = [circuit, parent]

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=True,
        )

        assert result["valid"] is True
        mock_recompute.assert_called_once_with(config_path)
