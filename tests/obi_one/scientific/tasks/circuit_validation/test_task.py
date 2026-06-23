"""Tests for circuit validation task — unit-testable helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import pytest

from obi_one.scientific.tasks.circuit_validation.task import (
    _check_new_populations_not_biophysical,
    _collect_hoc_files,
    _find_stale_populations,
    _get_pop_config,
    _read_model_templates,
    _write_dynamics_to_h5,
)

# ---------------------------------------------------------------------------
# _find_stale_populations
# ---------------------------------------------------------------------------


class TestFindStalePopulations:
    def test_no_stale(self):
        mapping = {"pop_a": {"new_id": [0, 1, 2], "parent_id": [0, 1, 2]}}
        pop_sizes = {"pop_a": 10}
        assert _find_stale_populations(mapping, pop_sizes) == []

    def test_stale_detected(self):
        mapping = {"pop_a": {"new_id": [0, 5, 99]}}
        pop_sizes = {"pop_a": 50}  # max new_id=99 >= 50
        result = _find_stale_populations(mapping, pop_sizes)
        assert len(result) == 1
        assert "pop_a" in result[0]
        assert "99" in result[0]

    def test_missing_population_in_sizes(self):
        mapping = {"pop_a": {"new_id": [0, 999]}}
        pop_sizes = {}  # pop_a not in sizes → skip
        assert _find_stale_populations(mapping, pop_sizes) == []

    def test_empty_new_ids(self):
        mapping = {"pop_a": {"new_id": []}}
        pop_sizes = {"pop_a": 10}
        assert _find_stale_populations(mapping, pop_sizes) == []

    def test_non_dict_entry_skipped(self):
        mapping = {"pop_a": "not a dict"}
        pop_sizes = {"pop_a": 10}
        assert _find_stale_populations(mapping, pop_sizes) == []


# ---------------------------------------------------------------------------
# _get_pop_config
# ---------------------------------------------------------------------------


class TestGetPopConfig:
    def test_found(self):
        cfg = {
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "nodes.h5",
                        "populations": {
                            "pop_a": {"type": "biophysical", "morphologies_dir": "/m"},
                        },
                    }
                ]
            }
        }
        result = _get_pop_config(cfg, "pop_a")
        assert result == {"type": "biophysical", "morphologies_dir": "/m"}

    def test_not_found(self):
        cfg = {"networks": {"nodes": [{"populations": {"other": {}}}]}}
        assert _get_pop_config(cfg, "pop_a") is None

    def test_empty_config(self):
        assert _get_pop_config({}, "pop_a") is None


# ---------------------------------------------------------------------------
# _read_model_templates
# ---------------------------------------------------------------------------


class TestReadModelTemplates:
    def test_reads_templates(self, tmp_path):
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset(
                "model_template",
                data=[b"hoc:CellA", b"hoc:CellB", b"hoc:CellA"],
            )
        result = _read_model_templates(str(nodes_file), "pop_a")
        assert result == {"hoc:CellA", "hoc:CellB"}

    def test_missing_population(self, tmp_path):
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            f.create_group("nodes/other/0")
        result = _read_model_templates(str(nodes_file), "pop_a")
        assert result == set()

    def test_no_model_template_column(self, tmp_path):
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("morphology", data=[b"morph1"])
        result = _read_model_templates(str(nodes_file), "pop_a")
        assert result == set()

    def test_corrupted_file(self, tmp_path):
        nodes_file = tmp_path / "nodes.h5"
        nodes_file.write_text("not hdf5")
        result = _read_model_templates(str(nodes_file), "pop_a")
        assert result == set()


# ---------------------------------------------------------------------------
# _collect_hoc_files
# ---------------------------------------------------------------------------


class TestCollectHocFiles:
    def test_collects_from_component_dir(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "CellA.hoc").write_text("begintemplate CellA\nendtemplate CellA\n")
        (hoc_dir / "CellB.hoc").write_text("begintemplate CellB\nendtemplate CellB\n")
        (hoc_dir / "not_hoc.txt").write_text("ignored")

        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {"nodes": [{"populations": {"pop_a": {"type": "biophysical"}}}]},
        }
        result = _collect_hoc_files(cfg, tmp_path)
        assert len(result) == 2
        assert all(f.suffix == ".hoc" for f in result)

    def test_empty_when_no_dir(self, tmp_path):
        cfg = {
            "components": {},
            "networks": {"nodes": [{"populations": {"pop_a": {}}}]},
        }
        assert _collect_hoc_files(cfg, tmp_path) == []

    def test_skips_virtual_populations(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "cell.hoc").write_text("x")

        cfg = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {"nodes": [{"populations": {"virt": {"type": "virtual"}}}]},
        }
        assert _collect_hoc_files(cfg, tmp_path) == []


# ---------------------------------------------------------------------------
# _write_dynamics_to_h5
# ---------------------------------------------------------------------------


class TestWriteDynamicsToH5:
    def _make_circuit(self, tmp_path, pop_name="pop_a", n_nodes=10):
        """Create a minimal circuit config + nodes H5 for testing."""
        nodes_file = tmp_path / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            grp = f.create_group(f"nodes/{pop_name}/0")
            grp.create_dataset("morphology", data=[b"m"] * n_nodes)
            f[f"nodes/{pop_name}"].create_dataset(
                "node_type_id", data=np.zeros(n_nodes, dtype=np.int32)
            )

        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(
            '{"manifest":{"$BASE_DIR":"' + str(tmp_path) + '"},'
            '"networks":{"nodes":[{"nodes_file":"' + str(nodes_file) + '",'
            '"populations":{"' + pop_name + '":{}}}],"edges":[]}}'
        )
        return config_path, nodes_file

    def test_creates_dynamics_params(self, tmp_path):
        config_path, nodes_file = self._make_circuit(tmp_path, n_nodes=5)

        holding = {0: 0.1, 2: 0.3, 4: 0.5}
        threshold = {0: 1.0, 2: 3.0, 4: 5.0}

        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:
            mock_cfg.return_value.expanded_json = (
                '{"networks":{"nodes":[{"nodes_file":"'
                + str(nodes_file)
                + '","populations":{"pop_a":{}}}]}}'
            )
            _write_dynamics_to_h5(config_path, "pop_a", holding, threshold)

        with h5py.File(nodes_file, "r") as f:
            dyn = f["nodes/pop_a/0/dynamics_params"]
            assert "holding_current" in dyn
            assert "threshold_current" in dyn
            assert dyn["holding_current"][0] == pytest.approx(0.1)
            assert dyn["holding_current"][2] == pytest.approx(0.3)
            assert dyn["threshold_current"][4] == pytest.approx(5.0)
            # Unset nodes should be 0
            assert dyn["holding_current"][1] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _check_new_populations_not_biophysical
# ---------------------------------------------------------------------------


class TestCheckNewPopulationsNotBiophysical:
    """New populations must be virtual or point_neuron, not biophysical."""

    def _make_config(self, tmp_path, name, populations):
        """Create a minimal circuit_config.json with given populations."""
        cfg = {
            "manifest": {"$BASE_DIR": str(tmp_path)},
            "networks": {
                "nodes": [{"nodes_file": "nodes.h5", "populations": populations}],
                "edges": [],
            },
        }
        path = tmp_path / name
        path.write_text(json.dumps(cfg))
        return path

    def test_new_virtual_allowed(self, tmp_path):
        parent = self._make_config(tmp_path, "parent.json", {"pop_a": {"type": "biophysical"}})
        child = self._make_config(
            tmp_path,
            "child.json",
            {"pop_a": {"type": "biophysical"}, "new_virt": {"type": "virtual"}},
        )
        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:

            def side_effect(path):
                m = MagicMock()
                m.expanded_json = Path(path).read_text(encoding="utf-8")
                return m

            mock_cfg.side_effect = side_effect

            errors = _check_new_populations_not_biophysical(child, parent)
        assert errors == []

    def test_new_biophysical_rejected(self, tmp_path):
        parent = self._make_config(tmp_path, "parent.json", {"pop_a": {"type": "biophysical"}})
        child = self._make_config(
            tmp_path,
            "child.json",
            {"pop_a": {"type": "biophysical"}, "new_bio": {"type": "biophysical"}},
        )
        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:

            def side_effect(path):
                m = MagicMock()
                m.expanded_json = Path(path).read_text(encoding="utf-8")
                return m

            mock_cfg.side_effect = side_effect

            errors = _check_new_populations_not_biophysical(child, parent)
        assert len(errors) == 1
        assert "new_bio" in errors[0]

    def test_new_point_neuron_allowed(self, tmp_path):
        parent = self._make_config(tmp_path, "parent.json", {"pop_a": {}})
        child = self._make_config(
            tmp_path,
            "child.json",
            {"pop_a": {}, "new_pn": {"type": "point_neuron"}},
        )
        with patch(
            "obi_one.scientific.tasks.circuit_validation.task.libsonata.CircuitConfig.from_file"
        ) as mock_cfg:

            def side_effect(path):
                m = MagicMock()
                m.expanded_json = Path(path).read_text(encoding="utf-8")
                return m

            mock_cfg.side_effect = side_effect

            errors = _check_new_populations_not_biophysical(child, parent)
        assert errors == []
