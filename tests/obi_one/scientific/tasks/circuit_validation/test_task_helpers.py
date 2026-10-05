"""Unit tests for circuit validation task helpers — additional coverage."""

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import pandas as pd
import pytest
from bluepysnap import Circuit
from bluepysnap.exceptions import BluepySnapError

from obi_one.scientific.library.circuit_id_mapping import (
    get_population_sizes,
    validate_id_mapping_files,
)
from obi_one.scientific.tasks.circuit_validation.task import (
    _compile_mechanisms,
    _find_mod_dir,
    _find_morphology_for_template,
    _load_compiled_mechanisms,
    _mechanism_suffixes_from_mod_dir,
    _validate_emodel_paths,
    _validate_hoc_loading,
    _validate_morphology_paths,
)

from tests.utils import CIRCUIT_DIR

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

        assert get_population_sizes(mock_circuit) == {"pop_a": 42, "pop_b": 10}

    def test_empty_populations(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = []
        assert get_population_sizes(mock_circuit) == {}


# ---------------------------------------------------------------------------
# _validate_morphology_paths
# ---------------------------------------------------------------------------


def _raise_not_configured(extension):
    """Mimic bluepysnap raising for a morphology format absent from the config."""
    msg = f"'{extension}' not configured"
    raise BluepySnapError(msg)


def _write_h5_container(path: Path, *cell_names: str) -> Path:
    """Write a minimal HDF5 morphology container with the given cell-name keys."""
    with h5py.File(path, "w") as f:
        for name in cell_names:
            f.create_group(name)
    return path


def _make_morph_pop(configured_extensions, *, unloadable_extensions=(), pop_type="biophysical"):
    """Build a mock biophysical population with the given configured morphology formats.

    ``configured_extensions`` are the formats resolvable in the config (others raise
    BluepySnapError, mimicking bluepysnap). Formats in ``unloadable_extensions`` resolve
    but fail to load (``pop.morph.get`` raises).
    """
    mock_pop = MagicMock()
    mock_pop.type = pop_type
    mock_pop.ids.return_value = [0, 1, 2]

    def get_morphology_base(extension):
        if extension in configured_extensions:
            return f"/morph/{extension}"
        msg = f"'{extension}' not configured"
        raise BluepySnapError(msg)

    def get(_node_id, extension="swc"):
        if extension in unloadable_extensions:
            msg = f"could not load .{extension}"
            raise ValueError(msg)
        return MagicMock()

    mock_pop.morph._get_morphology_base.side_effect = get_morphology_base
    mock_pop.morph.get.side_effect = get
    return mock_pop


def _make_morph_circuit(mock_pop, pop_name="pop_a"):
    mock_circuit = MagicMock()
    mock_circuit.nodes.population_names = [pop_name]
    mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop
    return mock_circuit


class TestValidateMorphologyPaths:
    def test_valid_swc_morphologies(self):
        """A loadable swc morphologies_dir — no error."""
        pop = _make_morph_pop(["swc"])
        errors = _validate_morphology_paths(_make_morph_circuit(pop))
        assert errors == []

    def test_valid_h5_container_only(self):
        """Only an H5 container is configured (no morphologies_dir) and loads — no error.

        This is the regression case: the old path check assumed an swc directory and
        wrongly failed H5-container-only circuits.
        """
        pop = _make_morph_pop(["h5"])
        errors = _validate_morphology_paths(_make_morph_circuit(pop))
        assert errors == []

    def test_configured_format_not_loadable(self):
        """A configured format that fails to load is a fatal error."""
        pop = _make_morph_pop(["h5"], unloadable_extensions=["h5"])
        errors = _validate_morphology_paths(_make_morph_circuit(pop))
        assert len(errors) == 1
        assert "not loadable" in errors[0]
        assert ".h5" in errors[0]

    def test_one_of_several_formats_not_loadable(self):
        """Every configured format is checked; one broken format flags the population."""
        pop = _make_morph_pop(["swc", "h5"], unloadable_extensions=["h5"])
        errors = _validate_morphology_paths(_make_morph_circuit(pop))
        assert len(errors) == 1
        assert ".h5" in errors[0]

    def test_no_morphology_format_configured(self):
        """No morphology format at all in the config is a fatal error."""
        pop = _make_morph_pop([])
        errors = _validate_morphology_paths(_make_morph_circuit(pop))
        assert len(errors) == 1
        assert "no morphology format" in errors[0]

    def test_skips_virtual_populations(self):
        """Virtual populations are skipped — no error."""
        pop = _make_morph_pop(["swc"], pop_type="virtual")
        errors = _validate_morphology_paths(_make_morph_circuit(pop))
        assert errors == []

    def test_real_h5_container_circuit(self):
        """Integration: a real circuit whose only morphology source is an H5 container.

        Regression guard for the H5-container-only case (no morphologies_dir), which the
        previous swc-assuming implementation wrongly flagged. Uses bluepysnap end-to-end
        rather than mocks, so it would catch a reintroduction of the private-API coupling.
        """
        config_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
        circuit = Circuit(str(config_path))

        errors = _validate_morphology_paths(circuit)

        assert errors == []

    def test_real_swc_circuit(self):
        """Integration: a real circuit whose morphologies are a file-based swc directory."""
        config_path = CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5" / "circuit_config.json"
        circuit = Circuit(str(config_path))

        errors = _validate_morphology_paths(circuit)

        assert errors == []


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
            "obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = validate_id_mapping_files(config_path, MagicMock())
        assert result == []

    def test_missing_id_mapping_file(self, tmp_path):
        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": []},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        with patch(
            "obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = validate_id_mapping_files(config_path, MagicMock())
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
                "obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file"
            ) as mock_cfg,
            patch(
                "obi_one.scientific.library.circuit_id_mapping.get_population_sizes",
                return_value={"pop_a": 10},
            ),
        ):
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = validate_id_mapping_files(config_path, MagicMock())
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
                "obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file"
            ) as mock_cfg,
            patch(
                "obi_one.scientific.library.circuit_id_mapping.get_population_sizes",
                return_value={"pop_a": 100},
            ),
        ):
            m = MagicMock()
            m.expanded_json = json.dumps(cfg)
            mock_cfg.return_value = m

            result = validate_id_mapping_files(config_path, MagicMock())
        assert result == []


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
    @patch("obi_one.scientific.tasks.circuit_validation.task.run_validation")
    @patch("obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_passes_with_no_errors(
        self,
        mock_snap_circuit,  # ruff: ignore[unused-method-argument]
        mock_libsonata_cfg,
        mock_run_validation,
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

        mock_run_validation.return_value = ([], [])  # no errors / warnings
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
        )

        assert result["valid"] is True
        assert result["errors"] == []
        mock_run_validation.assert_called_once_with(config_path, raise_on_error=False)
        mock_update_status.assert_called_once_with(db_client, circuit_id, "active")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_emodel_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_morphology_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_mod_dir")
    @patch("obi_one.scientific.tasks.circuit_validation.task.run_validation")
    @patch("obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_passes_with_warnings_logged(
        self,
        mock_snap_circuit,  # ruff: ignore[unused-method-argument]
        mock_libsonata_cfg,
        mock_run_validation,
        mock_find_mod_dir,
        mock_morph_paths,
        mock_emodel_paths,
        mock_hoc_loading,
        mock_update_status,
        mock_stage,
        tmp_path,
        caplog,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
            run_circuit_validation,
        )

        config_path, _circuit_dir = self._make_minimal_circuit(tmp_path)

        mock_stage.return_value = config_path
        mock_find_mod_dir.return_value = None
        mock_morph_paths.return_value = []
        mock_emodel_paths.return_value = []
        mock_hoc_loading.return_value = []
        mock_run_validation.return_value = ([], ["partial circuit warning"])

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        circuit.generated_from_derivations = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        with caplog.at_level("WARNING"):
            result = run_circuit_validation(
                db_client=db_client,
                circuit_id=circuit_id,
            )

        assert result["valid"] is True
        assert result["warnings"] == ["partial circuit warning"]
        assert any("partial circuit warning" in r.message for r in caplog.records)
        mock_update_status.assert_called_once_with(db_client, circuit_id, "active")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.run_validation")
    @patch("obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_fails_with_missing_morphology_dir(
        self,
        mock_bluepysnap_circuit,
        mock_libsonata_cfg,
        mock_run_validation,
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

        # Mock bluepysnap.Circuit so that morphology loading fails: swc is configured
        # but cannot be loaded.
        mock_pop = _make_morph_pop(["swc"], unloadable_extensions=["swc"])
        mock_pop.ids.return_value = [0]
        mock_circuit_instance = _make_morph_circuit(mock_pop)
        mock_bluepysnap_circuit.return_value = mock_circuit_instance

        mock_run_validation.return_value = ([], [])
        mock_hoc_loading.return_value = []

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.generated_from_derivations = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
        )

        assert result["valid"] is False
        assert any("not loadable" in e for e in result["errors"])
        mock_update_status.assert_called_once_with(db_client, circuit_id, "disqualified")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._compile_mechanisms")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_mod_dir")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_emodel_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_morphology_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task.run_validation")
    @patch("obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_mod_compilation_failure(
        self,
        mock_snap_circuit,  # ruff: ignore[unused-method-argument]
        mock_libsonata_cfg,
        mock_run_validation,  # ruff: ignore[unused-method-argument]
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
        )

        assert result["valid"] is False
        assert any("nrnivmodl" in e for e in result["errors"])
        mock_update_status.assert_called_once_with(db_client, circuit_id, "disqualified")

    @patch("obi_one.scientific.tasks.circuit_validation.task.stage_circuit")
    @patch("obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_hoc_loading")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_emodel_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._validate_morphology_paths")
    @patch("obi_one.scientific.tasks.circuit_validation.task._find_mod_dir")
    @patch("obi_one.scientific.tasks.circuit_validation.task.run_validation")
    @patch("obi_one.scientific.library.circuit_id_mapping.libsonata.CircuitConfig.from_file")
    @patch("bluepysnap.Circuit")
    def test_run_validation_failure_is_logged_as_fatal(
        self,
        mock_snap_circuit,  # ruff: ignore[unused-method-argument]
        mock_libsonata_cfg,
        mock_run_validation,
        mock_find_mod_dir,
        mock_morph_paths,
        mock_emodel_paths,
        mock_hoc_loading,
        mock_update_status,
        mock_stage,
        tmp_path,
        caplog,
    ):
        from uuid import uuid4  # ruff: ignore[import-outside-top-level]

        from obi_one.scientific.tasks.circuit_validation.task import (  # ruff: ignore[import-outside-top-level]
            run_circuit_validation,
        )

        config_path, _circuit_dir = self._make_minimal_circuit(tmp_path)

        mock_stage.return_value = config_path
        mock_find_mod_dir.return_value = None
        mock_morph_paths.return_value = []
        mock_emodel_paths.return_value = []
        mock_hoc_loading.return_value = []
        mock_run_validation.return_value = (
            ["missing edge property"],
            ["partial circuit warning"],
        )

        mock_cfg_obj = MagicMock()
        mock_cfg_obj.expanded_json = config_path.read_text()
        mock_libsonata_cfg.return_value = mock_cfg_obj

        db_client = MagicMock()
        circuit = MagicMock()
        circuit.root_circuit_id = None
        circuit.generated_from_derivations = None
        db_client.get_entity.return_value = circuit

        circuit_id = uuid4()

        with caplog.at_level("WARNING"):
            result = run_circuit_validation(
                db_client=db_client,
                circuit_id=circuit_id,
            )

        assert result["valid"] is False
        assert "missing edge property" in result["errors"]
        assert "partial circuit warning" in result["warnings"]
        assert any("missing edge property" in r.message for r in caplog.records)
        assert any("partial circuit warning" in r.message for r in caplog.records)
        mock_update_status.assert_called_once_with(db_client, circuit_id, "disqualified")


# ---------------------------------------------------------------------------
# _validate_hoc_loading
# ---------------------------------------------------------------------------


class TestValidateHocLoading:
    def _make_circuit_with_used_template(
        self,
        *,
        hoc_file: Path,
        morph_file: Path | None,
        template_ref: str = "hoc:Cell",
        h5_container: Path | None = None,
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

        # Model an H5 container (no standalone morphology file): get_filepath fails for
        # every extension, and _get_morphology_base("h5") points at the container file.
        if h5_container is not None:
            mock_pop.morph.get_filepath.side_effect = Exception("no standalone file")
            mock_pop.morph._get_morphology_base.side_effect = lambda ext: (
                str(h5_container) if ext == "h5" else _raise_not_configured(ext)
            )

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

    def test_container_morph_with_incompatible_old_hoc_is_error(self, tmp_path):
        """An H5-container morphology + an old HOC without .h5 support is a fatal error."""
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "OldCell.hoc"
        # Old template: load_morphology handles only asc/swc, no morphio_read.
        hoc_file.write_text(
            "begintemplate OldCell\nproc load_morphology() {}\nendtemplate OldCell\n"
        )
        container = _write_h5_container(tmp_path / "merged-morphologies.h5", "cell")

        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=hoc_file, morph_file=None, template_ref="hoc:OldCell", h5_container=container
        )

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)
        assert len(result) == 1
        assert "does not support H5 container morphologies" in result[0]

    @patch("obi_one.scientific.validations.emodels.bluecellulab_initializable")
    def test_container_morph_with_compatible_hoc_instantiates(self, mock_init, tmp_path):
        """An H5-container morphology + a container-capable HOC proceeds to instantiation."""
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "NewCell.hoc"
        # New template: load_morphology calls morphio_read for the .h5 branch.
        hoc_file.write_text(
            "begintemplate NewCell\nproc load_morphology() { morphio_read(this, morph_path) }\n"
            "endtemplate NewCell\n"
        )
        container = _write_h5_container(tmp_path / "merged-morphologies.h5", "cell")

        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=hoc_file, morph_file=None, template_ref="hoc:NewCell", h5_container=container
        )

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False)

        assert result == []
        mock_init.assert_called_once()
        # bluecellulab receives the container-style path <container>.h5/<cell_name>.
        morph_arg = str(mock_init.call_args[0][1])
        assert morph_arg.endswith("merged-morphologies.h5/cell")

    def test_container_missing_morphology_key_is_error(self, tmp_path):
        """A container that lacks the referenced morphology key is a fatal error."""
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "NewCell.hoc"
        hoc_file.write_text(
            "begintemplate NewCell\nproc load_morphology() { morphio_read(this, morph_path) }\n"
            "endtemplate NewCell\n"
        )
        # Container exists but does not contain the "cell" morphology.
        container = _write_h5_container(tmp_path / "merged-morphologies.h5", "other_cell")

        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=hoc_file, morph_file=None, template_ref="hoc:NewCell", h5_container=container
        )

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

    @patch("obi_one.scientific.validations.emodels.bluecellulab_initializable")
    def test_missing_used_mechanism_fails_before_instantiate(self, mock_init, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        hoc_file = hoc_dir / "Cell.hoc"
        hoc_file.write_text(
            "begintemplate Cell\n"
            "proc init() {\n"
            "    insert pas\n"
            "    insert CaDynamics_DC0\n"
            "}\n"
            "endtemplate Cell\n"
        )
        morph_path = tmp_path / "morph.swc"
        morph_path.write_text("fake morph")
        mod_dir = tmp_path / "mod"
        mod_dir.mkdir()
        (mod_dir / "Ih.mod").write_text("NEURON {\n    SUFFIX Ih\n}\n")
        mock_circuit = self._make_circuit_with_used_template(
            hoc_file=hoc_file, morph_file=morph_path, template_ref="hoc:Cell"
        )

        result = _validate_hoc_loading(mock_circuit, tmp_path, load_mods=False, mod_dir=mod_dir)

        assert len(result) == 1
        assert "mechanism check failed" in result[0]
        assert "CaDynamics_DC0" in result[0]
        mock_init.assert_not_called()

    def test_mechanism_suffixes_from_mod_dir(self, tmp_path):
        mod_dir = tmp_path / "mod"
        mod_dir.mkdir()
        (mod_dir / "a.mod").write_text("NEURON {\n\tSUFFIX Ca_HVA2\n}\n")
        (mod_dir / "b.mod").write_text("NEURON {\n POINT_PROCESS DetAMPANMDA\n}\n")

        assert _mechanism_suffixes_from_mod_dir(mod_dir) == {"Ca_HVA2", "DetAMPANMDA"}


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
