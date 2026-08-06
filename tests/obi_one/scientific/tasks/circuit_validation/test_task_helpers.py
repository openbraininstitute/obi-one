"""Unit tests for circuit validation task helpers — additional coverage."""

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import pandas as pd
import pytest

from obi_one.scientific.tasks.circuit_validation.task import (
    _compile_mechanisms,
    _find_mod_dir,
    _find_morphology_for_template,
    _get_population_sizes,
    _load_compiled_mechanisms,
    _update_h5_dataset,
    _validate_emodel_paths,
    _validate_hoc_loading,
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
        (mod_dir / "Na.mod").write_text("NEURON { SUFFIX na }\n")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.config = {"mechanisms_dir": str(mod_dir)}
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        assert _find_mod_dir(mock_circuit) == mod_dir

    def test_returns_nested_mod_subdirectory(self, tmp_path):
        circuit_root = tmp_path / "circuit"
        nested = circuit_root / "mod"
        nested.mkdir(parents=True)
        (nested / "Ca.mod").write_text("NEURON { SUFFIX ca }\n")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.config = {"mechanisms_dir": str(circuit_root)}
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        assert _find_mod_dir(mock_circuit) == nested

    def test_returns_none_when_no_mechanisms_dir(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.config = {}
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        assert _find_mod_dir(mock_circuit) is None


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
# _load_compiled_mechanisms
# ---------------------------------------------------------------------------


class TestLoadCompiledMechanisms:
    def test_noop_when_no_arch_dir(self, tmp_path):
        with patch("neuron.load_mechanisms") as mock_load:
            _load_compiled_mechanisms(tmp_path)
        mock_load.assert_not_called()

    def test_uses_neuron_load_mechanisms_for_arm64(self, tmp_path):
        (tmp_path / "arm64").mkdir()
        with patch("neuron.load_mechanisms") as mock_load:
            _load_compiled_mechanisms(tmp_path)
        mock_load.assert_called_once_with(str(tmp_path))

    def test_uses_neuron_load_mechanisms_for_x86_64(self, tmp_path):
        (tmp_path / "x86_64").mkdir()
        with patch("neuron.load_mechanisms") as mock_load:
            _load_compiled_mechanisms(tmp_path)
        mock_load.assert_called_once_with(str(tmp_path))


# ---------------------------------------------------------------------------
# _get_population_sizes
# ---------------------------------------------------------------------------


class TestGetPopulationSizes:
    def test_reads_sizes(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a", "pop_b"]
        mock_pop_a = MagicMock()
        mock_pop_a.size = 42
        mock_pop_b = MagicMock()
        mock_pop_b.size = 10
        mock_circuit.nodes.__getitem__ = lambda _self, k: mock_pop_a if k == "pop_a" else mock_pop_b

        assert _get_population_sizes(mock_circuit) == {"pop_a": 42, "pop_b": 10}

    def test_empty_populations(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = []
        assert _get_population_sizes(mock_circuit) == {}


# ---------------------------------------------------------------------------
# _validate_morphology_paths
# ---------------------------------------------------------------------------


class TestValidateMorphologyPaths:
    def test_valid_morphology_files(self, tmp_path):
        """All sampled morphology files exist — no error."""
        morph_file = tmp_path / "cell.swc"
        morph_file.write_text("mock")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.ids.return_value = [0, 1, 2]
        mock_pop.morph.get_filepath.return_value = str(morph_file)
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        errors = _validate_morphology_paths(mock_circuit)
        assert errors == []

    def test_missing_morphology_file(self):
        """Morphology file doesn't exist on disk — error reported."""
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.ids.return_value = [0]
        mock_pop.morph.get_filepath.return_value = "/nonexistent/cell.swc"
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_morphology_paths(mock_circuit)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_skips_virtual_populations(self):
        """Virtual populations are skipped — no error."""
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["virt"]
        mock_pop = MagicMock()
        mock_pop.type = "virtual"
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_morphology_paths(mock_circuit)
        assert errors == []

    def test_get_filepath_raises(self):
        """get_filepath raises (e.g. H5 container missing morphology) — error reported."""
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.ids.return_value = [0]
        mock_pop.morph.get_filepath.side_effect = Exception("morphology not in container")
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_morphology_paths(mock_circuit)
        assert len(errors) == 1
        assert "not accessible" in errors[0]


# ---------------------------------------------------------------------------
# _validate_emodel_paths
# ---------------------------------------------------------------------------


class TestValidateEmodelPaths:
    def _mock_pop(
        self,
        *,
        hoc_dir: str | None,
        templates: list[str],
        pop_type: str = "biophysical",
        all_values: list[str] | None = None,
    ):
        mock_pop = MagicMock()
        mock_pop.type = pop_type
        mock_pop.config = {"biophysical_neuron_models_dir": hoc_dir} if hoc_dir else {}
        mock_pop.property_names = {"model_template"} if templates is not None else set()
        values = all_values if all_values is not None else templates
        series = MagicMock()
        series.tolist.return_value = values
        series.unique.return_value.tolist.return_value = list(dict.fromkeys(values))
        mock_pop.get.return_value = series
        return mock_pop

    def test_valid_hoc_files_exist(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "CellA.hoc").write_text("begintemplate CellA\nendtemplate CellA\n")
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = self._mock_pop(hoc_dir=str(hoc_dir), templates=["hoc:CellA"])
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_emodel_paths(mock_circuit)
        assert errors == []

    def test_missing_hoc_file(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = self._mock_pop(hoc_dir=str(hoc_dir), templates=["hoc:CellA"])
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_emodel_paths(mock_circuit)
        assert len(errors) == 1
        assert "CellA.hoc" in errors[0]
        assert "not found" in errors[0]

    def test_missing_hoc_dir(self, tmp_path):
        missing = str(tmp_path / "nonexistent")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = self._mock_pop(hoc_dir=missing, templates=["hoc:CellA"])
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        errors = _validate_emodel_paths(mock_circuit)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_skips_virtual_populations(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["virt"]
        mock_pop = self._mock_pop(
            hoc_dir="/nonexistent", templates=["hoc:CellA"], pop_type="virtual"
        )
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_emodel_paths(mock_circuit)
        assert errors == []

    def test_resolved_hoc_dir_from_snap(self, tmp_path):
        """SNAP returns an already-resolved absolute hoc dir in population.config."""
        hoc_dir = tmp_path / "relative_hoc"
        hoc_dir.mkdir()
        (hoc_dir / "MyCell.hoc").write_text("template")
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = self._mock_pop(hoc_dir=str(hoc_dir), templates=["hoc:MyCell"])
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_emodel_paths(mock_circuit)
        assert errors == []

    def test_empty_model_template_is_error(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "CellA.hoc").write_text("template")
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = self._mock_pop(
            hoc_dir=str(hoc_dir),
            templates=["hoc:CellA", ""],
            all_values=["hoc:CellA", ""],
        )
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_emodel_paths(mock_circuit)
        assert any("empty model_template" in e for e in errors)

    def test_missing_models_dir_when_templates_present(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = self._mock_pop(hoc_dir=None, templates=["hoc:CellA"])
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        errors = _validate_emodel_paths(mock_circuit)
        assert any("biophysical_neuron_models_dir is not configured" in e for e in errors)


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

            result = _validate_id_mapping_files(config_path, MagicMock())
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

            result = _validate_id_mapping_files(config_path, MagicMock())
        assert result == []  # file doesn't exist => nothing to validate

    def test_stale_mapping_removed(self, tmp_path):
        # Create id_mapping with stale new_ids
        id_mapping = tmp_path / "id_mapping.json"
        id_mapping.write_text(json.dumps({"pop_a": {"new_id": [0, 99]}}))

        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": []},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with (
            patch(
                "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
            ) as mock_cfg,
            patch(
                "obi_one.scientific.tasks.circuit_validation.task._get_population_sizes",
                return_value={"pop_a": 10},
            ),
        ):
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _validate_id_mapping_files(config_path, MagicMock())
        assert len(result) == 1
        assert "stale" in result[0]
        assert "removed" in result[0]
        assert not id_mapping.exists()

    def test_valid_mapping(self, tmp_path):
        id_mapping = tmp_path / "id_mapping.json"
        id_mapping.write_text(json.dumps({"pop_a": {"new_id": [0, 5, 9]}}))

        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": []},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with (
            patch(
                "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
            ) as mock_cfg,
            patch(
                "obi_one.scientific.tasks.circuit_validation.task._get_population_sizes",
                return_value={"pop_a": 100},
            ),
        ):
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = _validate_id_mapping_files(config_path, MagicMock())
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
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_emodel_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_morphology_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_mod_dir")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_passes_with_no_errors(
        self,
        mock_snap_circuit,  # ruff: ignore[unused-method-argument]
        mock_libsonata_cfg,
        mock_snap_validate,
        mock_find_mod_dir,
        mock_morph_paths,
        mock_emodel_paths,
        mock_hoc_loading,
        mock_update_status,
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
            run_circuit_validation,
        )

        config_path, _circuit_dir = self._make_minimal_circuit(tmp_path)

        # Setup mocks
        mock_stage.return_value = config_path
        mock_find_mod_dir.return_value = None
        mock_morph_paths.return_value = []
        mock_emodel_paths.return_value = []

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_cfg_obj.node_populations = ["pop_a"]
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []  # no errors
        mock_hoc_loading.return_value = []  # no errors

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        circuit.generated_from_derivations = None
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
    @patch("bluepysnap.Circuit")
    def test_fails_with_missing_morphology_dir(
        self,
        mock_bluepysnap_circuit,
        mock_libsonata_cfg,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
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

        # Mock bluepysnap.Circuit so that morph lookup fails
        mock_circuit_instance = MagicMock()
        mock_circuit_instance.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.ids.return_value = [0]
        mock_pop.morph.get_filepath.side_effect = Exception("morphologies_dir does not exist")
        mock_circuit_instance.nodes.__getitem__ = lambda _self, _k: mock_pop
        mock_bluepysnap_circuit.return_value = mock_circuit_instance

        mock_snap_validate.validate.return_value = []
        mock_hoc_loading.return_value = []

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.generated_from_derivations = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=False,
        )

        assert result["valid"] is False
        assert any("not accessible" in e for e in result["errors"])
        mock_update_status.assert_called_once_with(db_client, circuit_id, "disqualified")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._compile_mechanisms")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_mod_dir")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_emodel_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_morphology_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_mod_compilation_failure(
        self,
        mock_snap_circuit,  # ruff: ignore[unused-method-argument]
        mock_libsonata_cfg,
        mock_snap_validate,  # ruff: ignore[unused-method-argument]
        mock_hoc_loading,
        mock_morph_paths,
        mock_emodel_paths,
        mock_find_mod_dir,
        mock_compile,
        mock_update_status,
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
            run_circuit_validation,
        )

        config_path, circuit_dir = self._make_minimal_circuit(tmp_path)

        # Add a mechanisms_dir with a .mod file
        mod_dir = circuit_dir / "mechanisms"
        mod_dir.mkdir()
        (mod_dir / "NaTg.mod").write_text("NEURON { SUFFIX NaTg }\n")

        mock_stage.return_value = config_path
        mock_find_mod_dir.return_value = mod_dir
        mock_morph_paths.return_value = []
        mock_emodel_paths.return_value = []
        mock_hoc_loading.return_value = []

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_compile.side_effect = RuntimeError("nrnivmodl failed: syntax error")

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        circuit.generated_from_derivations = None
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
    def _make_circuit_with_used_template(
        self, *, hoc_file: Path, morph_file: Path | None, template_ref: str = "hoc:Cell"
    ):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.config = {"biophysical_neuron_models_dir": str(hoc_file.parent)}
        mock_pop.property_names = {"model_template", "morphology"}
        mock_pop.get.return_value = pd.DataFrame(
            {"model_template": [template_ref], "morphology": ["cell"]},
            index=[0],
        )
        if morph_file is None:
            mock_pop.morph.get_filepath.side_effect = Exception("missing morph")
        else:
            mock_pop.morph.get_filepath.return_value = str(morph_file)
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
        return mock_circuit

    def test_no_used_templates_returns_empty(self, tmp_path):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = []
        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)
        assert result == []

    def test_missing_morphology_is_error(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "Cell.hoc"
        hoc_file.write_text("begintemplate Cell\nendtemplate Cell\n")
        mock_circuit = self._make_circuit_with_used_template(hoc_file=hoc_file, morph_file=None)

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)
        assert len(result) == 1
        assert "could not resolve morphology" in result[0]

    @patch("obi_one.scientific.validations.emodels.bluecellulab_initializable")
    def test_hoc_instantiation_failure(self, mock_init, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "BadCell.hoc"
        hoc_file.write_text("begintemplate BadCell\nendtemplate BadCell\n")
        morph_path = tmp_path / "morph.swc"
        morph_path.write_text("fake morph")
        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=hoc_file, morph_file=morph_path, template_ref="hoc:BadCell"
        )
        mock_init.side_effect = RuntimeError("NEURON crash")

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)

        assert len(result) == 1
        assert "BadCell.hoc" in result[0]
        assert "failed to instantiate" in result[0]

    @patch("obi_one.scientific.validations.emodels.bluecellulab_initializable")
    def test_hoc_success(self, mock_init, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "GoodCell.hoc"
        hoc_file.write_text("begintemplate GoodCell\nendtemplate GoodCell\n")
        morph_path = tmp_path / "morph.swc"
        morph_path.write_text("fake morph")
        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=hoc_file, morph_file=morph_path, template_ref="hoc:GoodCell"
        )

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)
        assert result == []
        mock_init.assert_called_once()

    def test_missing_hoc_file_for_used_template(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        # referenced HOC file intentionally absent
        missing_hoc = hoc_dir / "Missing.hoc"
        morph_path = tmp_path / "morph.swc"
        morph_path.write_text("fake morph")
        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=missing_hoc, morph_file=morph_path, template_ref="hoc:Missing"
        )

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)
        assert len(result) == 1
        assert "Missing.hoc" in result[0]
        assert "not found" in result[0]


class TestFindMorphologyForTemplate:
    def test_uses_get_filepath(self, tmp_path):
        morph_file = tmp_path / "cell.swc"
        morph_file.write_text("fake")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.property_names = {"model_template", "morphology"}
        mock_pop.get.return_value = pd.DataFrame(
            {"model_template": ["hoc:CellA"], "morphology": ["cell"]},
            index=[7],
        )
        mock_pop.morph.get_filepath.return_value = str(morph_file)
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        result = _find_morphology_for_template("CellA", mock_circuit)
        assert result == morph_file
        mock_pop.morph.get_filepath.assert_called()


# ---------------------------------------------------------------------------
# _check_content_subset_of_parent
# ---------------------------------------------------------------------------


class TestCheckContentSubsetOfParent:
    def test_child_is_subset(self):
        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
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

        errors = _check_content_subset_of_parent(child, parent)
        assert errors == []

    def test_child_has_extra_morphologies(self):
        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
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

        errors = _check_content_subset_of_parent(child, parent)
        assert len(errors) == 1
        assert "morphology" in errors[0]


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
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_subset_checks_invoked_for_customization(
        self,
        mock_snap_circuit,
        mock_libsonata_cfg,
        mock_new_pops,
        mock_content_subset,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,  # ruff: ignore[unused-method-argument]
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
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
        snap = MagicMock()
        snap.nodes.population_names = []
        mock_snap_circuit.return_value = snap

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []
        mock_hoc_loading.return_value = []
        mock_new_pops.return_value = []
        mock_content_subset.return_value = []

        db_client = MagicMock()
        circuit = MagicMock()
        parent = MagicMock()
        parent.id = uuid4()
        # Set up derivation link so the validation finds the parent
        from entitysdk.types import DerivationType  # ruff: ignore[import-outside-top-level]

        deriv = MagicMock()
        deriv.used = parent
        deriv.derivation_type = DerivationType.circuit_customization
        circuit.generated_from_derivations = [deriv]
        db_client.get_entity.side_effect = [circuit, parent]

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=True,
        )

        assert result["valid"] is True
        mock_new_pops.assert_called_once()
        mock_content_subset.assert_called_once()

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.circuit_validation")
    @patch("obi_one.scientific.tasks.circuit_validation.task._check_content_subset_of_parent")
    @patch(
        "obi_one.scientific.tasks.circuit_validation.task._check_new_populations_not_biophysical"
    )
    @patch("obi_one.scientific.tasks.circuit_validation.task._recompute_dynamic_params")
    @patch("obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_recompute_dynamic_params_called(
        self,
        mock_snap_circuit,
        mock_libsonata_cfg,
        mock_recompute,
        mock_new_pops,
        mock_content_subset,
        mock_snap_validate,
        mock_hoc_loading,
        mock_update_status,  # ruff: ignore[unused-method-argument]
        mock_stage,
        tmp_path,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from entitysdk.types import DerivationType  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
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
        snap = MagicMock()
        snap.nodes.population_names = []
        mock_snap_circuit.return_value = snap

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        mock_snap_validate.validate.return_value = []
        mock_hoc_loading.return_value = []
        mock_new_pops.return_value = []
        mock_content_subset.return_value = []

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = uuid4()
        parent = MagicMock()
        parent.id = uuid4()
        deriv = MagicMock()
        deriv.used = parent
        deriv.derivation_type = DerivationType.circuit_customization
        circuit.generated_from_derivations = [deriv]
        db_client.get_entity.side_effect = [circuit, parent]

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=True,
        )

        assert result["valid"] is True
        mock_recompute.assert_called_once_with(snap, config_path)
