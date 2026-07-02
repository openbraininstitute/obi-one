"""Unit tests for circuit customization staging helpers."""

import json

import h5py
import numpy as np
import pytest

from obi_one.utils.circuit_customization.staging import (
    _apply_emodel_overrides,
    _apply_file_overrides,
    _apply_node_sets_override,
    _copy_into,
    _network_file_names,
    _remove_stale_network_files,
    _replace_file,
    _resolve_hoc_dir,
    _resolve_mod_dir,
)

# ---------------------------------------------------------------------------
# _resolve_hoc_dir
# ---------------------------------------------------------------------------


class TestResolveHocDir:
    def test_absolute_path(self, tmp_path):
        hoc_dir = tmp_path / "abs_hoc"
        config = {"components": {"biophysical_neuron_models_dir": str(hoc_dir)}}
        result = _resolve_hoc_dir(config, tmp_path / "circuit")
        assert result == hoc_dir
        assert result.exists()

    def test_relative_path(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = {"components": {"biophysical_neuron_models_dir": "models/hoc"}}
        result = _resolve_hoc_dir(config, circuit_dir)
        assert result == circuit_dir / "models" / "hoc"
        assert result.exists()

    def test_fallback_to_hoc(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = {"components": {}}
        result = _resolve_hoc_dir(config, circuit_dir)
        assert result == circuit_dir / "hoc"
        assert result.exists()


# ---------------------------------------------------------------------------
# _resolve_mod_dir
# ---------------------------------------------------------------------------


class TestResolveModDir:
    def test_absolute_path(self, tmp_path):
        mod_dir = tmp_path / "abs_mod"
        config = {"components": {"mechanisms_dir": str(mod_dir)}}
        result = _resolve_mod_dir(config, tmp_path / "circuit")
        assert result == mod_dir
        assert result.exists()

    def test_relative_path(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = {"components": {"mechanisms_dir": "mechanisms"}}
        result = _resolve_mod_dir(config, circuit_dir)
        assert result == circuit_dir / "mechanisms"
        assert result.exists()

    def test_fallback_to_mod(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = {"components": {}}
        result = _resolve_mod_dir(config, circuit_dir)
        assert result == circuit_dir / "mod"
        assert result.exists()


# ---------------------------------------------------------------------------
# _copy_into
# ---------------------------------------------------------------------------


class TestCopyInto:
    def test_copies_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        (src / "b.txt").write_text("beta")

        dest = tmp_path / "dest"
        dest.mkdir()

        _copy_into([src / "a.txt", src / "b.txt"], dest)
        assert (dest / "a.txt").read_text() == "alpha"
        assert (dest / "b.txt").read_text() == "beta"

    def test_overwrites_existing(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("new")

        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "file.txt").write_text("old")

        _copy_into([src / "file.txt"], dest)
        assert (dest / "file.txt").read_text() == "new"

    def test_replaces_symlink(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("override")

        dest = tmp_path / "dest"
        dest.mkdir()
        original = tmp_path / "original.txt"
        original.write_text("parent")
        (dest / "file.txt").symlink_to(original)

        _copy_into([src / "file.txt"], dest)
        assert not (dest / "file.txt").is_symlink()
        assert (dest / "file.txt").read_text() == "override"


# ---------------------------------------------------------------------------
# _replace_file
# ---------------------------------------------------------------------------


class TestReplaceFile:
    def test_replaces_regular_file(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("new content")
        target = tmp_path / "target.txt"
        target.write_text("old content")

        _replace_file(source, target)
        assert target.read_text() == "new content"

    def test_replaces_symlink(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("override")
        original = tmp_path / "original.txt"
        original.write_text("parent")
        target = tmp_path / "link.txt"
        target.symlink_to(original)

        _replace_file(source, target)
        assert not target.is_symlink()
        assert target.read_text() == "override"

    def test_creates_parent_dirs(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("content")
        target = tmp_path / "sub" / "dir" / "target.txt"

        _replace_file(source, target)
        assert target.read_text() == "content"


# ---------------------------------------------------------------------------
# _network_file_names
# ---------------------------------------------------------------------------


class TestNetworkFileNames:
    def test_collects_all_types(self):
        cfg = {
            "networks": {
                "nodes": [{"nodes_file": "/path/to/nodes.h5"}],
                "edges": [{"edges_file": "/path/to/edges.h5"}],
            },
            "node_sets_file": "/path/to/node_sets.json",
        }
        result = _network_file_names(cfg)
        assert result == {"nodes.h5", "edges.h5", "node_sets.json"}

    def test_empty_config(self):
        assert _network_file_names({}) == set()

    def test_multiple_files(self):
        cfg = {
            "networks": {
                "nodes": [
                    {"nodes_file": "a.h5"},
                    {"nodes_file": "b.h5"},
                ],
                "edges": [],
            },
        }
        result = _network_file_names(cfg)
        assert result == {"a.h5", "b.h5"}


# ---------------------------------------------------------------------------
# _apply_node_sets_override
# ---------------------------------------------------------------------------


class TestApplyNodeSetsOverride:
    def test_copies_and_patches_config(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps({"networks": {}}))

        node_sets = tmp_path / "my_node_sets.json"
        node_sets.write_text(json.dumps({"All": {"population": "default"}}))

        _apply_node_sets_override(node_sets, circuit_dir, config_path)

        assert (circuit_dir / "my_node_sets.json").exists()
        cfg = json.loads(config_path.read_text())
        assert cfg["node_sets_file"] == "my_node_sets.json"

    def test_does_not_patch_if_already_set(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps({"networks": {}, "node_sets_file": "existing.json"}))

        node_sets = tmp_path / "new_node_sets.json"
        node_sets.write_text(json.dumps({"All": {}}))

        _apply_node_sets_override(node_sets, circuit_dir, config_path)

        cfg = json.loads(config_path.read_text())
        assert cfg["node_sets_file"] == "existing.json"  # not changed

    def test_replaces_existing_symlink(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps({"node_sets_file": "ns.json"}))

        # Create a symlink in the circuit dir
        original = tmp_path / "parent_ns.json"
        original.write_text(json.dumps({"old": {}}))
        (circuit_dir / "new_ns.json").symlink_to(original)

        node_sets = tmp_path / "new_ns.json"
        node_sets.write_text(json.dumps({"new": {"population": "pop_a"}}))

        _apply_node_sets_override(node_sets, circuit_dir, config_path)
        # Symlink should be replaced with the actual file
        assert not (circuit_dir / "new_ns.json").is_symlink()


# ---------------------------------------------------------------------------
# _remove_stale_network_files
# ---------------------------------------------------------------------------


class TestRemoveStaleNetworkFiles:
    def test_removes_stale_symlinks(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        # Create a stale symlink (file referenced by parent but not by override)
        original = tmp_path / "parent_edges.h5"
        original.write_bytes(b"data")
        stale_link = circuit_dir / "old_edges.h5"
        stale_link.symlink_to(original)

        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(
            json.dumps({"networks": {"nodes": [], "edges": [{"edges_file": "new_edges.h5"}]}})
        )

        parent_config = {
            "networks": {"nodes": [], "edges": [{"edges_file": "old_edges.h5"}]},
        }

        _remove_stale_network_files(circuit_dir, config_path, parent_config)
        assert not stale_link.exists()

    def test_does_not_remove_non_symlinks(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        # Create a regular file (not a symlink — user upload)
        real_file = circuit_dir / "old_nodes.h5"
        real_file.write_bytes(b"data")

        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps({"networks": {"nodes": [], "edges": []}}))

        parent_config = {
            "networks": {"nodes": [{"nodes_file": "old_nodes.h5"}], "edges": []},
        }

        _remove_stale_network_files(circuit_dir, config_path, parent_config)
        assert real_file.exists()  # not removed because it's not a symlink


# ---------------------------------------------------------------------------
# _apply_file_overrides
# ---------------------------------------------------------------------------


class TestApplyFileOverrides:
    def _make_parent_edges(self, circuit_dir, pop_name="pop_a"):
        """Create a parent edges H5 file with a population."""
        edges_file = circuit_dir / "edges.h5"
        with h5py.File(edges_file, "w") as f:
            pop = f.create_group(f"edges/{pop_name}")
            n = 3
            pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))
        return edges_file

    def test_replaces_matching_population(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        parent_edges = self._make_parent_edges(circuit_dir, "pop_a")

        # Create override with same population but different data
        override = tmp_path / "new_edges.h5"
        with h5py.File(override, "w") as f:
            pop = f.create_group("edges/pop_a")
            n = 10
            pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))

        config = {
            "networks": {"edges": [{"edges_file": str(parent_edges)}]},
        }

        _apply_file_overrides([override], circuit_dir, config, component_type="edges")

        # Verify the file was replaced by checking the data length
        with h5py.File(parent_edges, "r") as f:
            assert f["edges/pop_a/source_node_id"].shape[0] == 10

    def test_unknown_population_raises(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        self._make_parent_edges(circuit_dir, "pop_a")

        override = tmp_path / "new_edges.h5"
        with h5py.File(override, "w") as f:
            f.create_group("edges/unknown_pop")

        config = {
            "networks": {"edges": [{"edges_file": str(circuit_dir / "edges.h5")}]},
        }

        with pytest.raises(ValueError, match="unknown_pop"):
            _apply_file_overrides([override], circuit_dir, config, component_type="edges")

    def test_nodes_override(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        nodes_file = circuit_dir / "nodes.h5"
        with h5py.File(nodes_file, "w") as f:
            f.create_group("nodes/pop_a")
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.zeros(5, dtype=np.int32))

        override = tmp_path / "new_nodes.h5"
        with h5py.File(override, "w") as f:
            f.create_group("nodes/pop_a")
            f["nodes/pop_a"].create_dataset("node_type_id", data=np.ones(10, dtype=np.int32))

        config = {
            "networks": {"nodes": [{"nodes_file": str(nodes_file)}]},
        }

        _apply_file_overrides([override], circuit_dir, config, component_type="nodes")

        # Verify the file was replaced (10 nodes instead of 5)
        with h5py.File(nodes_file, "r") as f:
            assert f["nodes/pop_a/node_type_id"].shape[0] == 10


# ---------------------------------------------------------------------------
# _apply_emodel_overrides
# ---------------------------------------------------------------------------


class TestApplyEmodelOverrides:
    def test_falls_back_to_component_dir(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        hoc_dir = circuit_dir / "hoc"
        hoc_dir.mkdir()

        hoc_file = tmp_path / "MyCell.hoc"
        hoc_file.write_text("begintemplate MyCell\nendtemplate MyCell\n")

        config = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {"nodes": [{"populations": {"pop_a": {}}}]},
        }

        _apply_emodel_overrides([hoc_file], {}, config, circuit_dir)
        assert (hoc_dir / "MyCell.hoc").exists()

    def test_places_in_population_dir(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        pop_dir = circuit_dir / "pop_hoc"
        pop_dir.mkdir()

        hoc_file = tmp_path / "PopCell.hoc"
        hoc_file.write_text("begintemplate PopCell\nendtemplate PopCell\n")

        config = {
            "components": {"biophysical_neuron_models_dir": str(circuit_dir / "hoc")},
            "networks": {
                "nodes": [
                    {
                        "populations": {
                            "pop_a": {
                                "biophysical_neuron_models_dir": str(pop_dir),
                            }
                        }
                    }
                ]
            },
        }

        _apply_emodel_overrides([hoc_file], {"PopCell.hoc": "pop_a"}, config, circuit_dir)
        assert (pop_dir / "PopCell.hoc").exists()

    def test_unmapped_file_goes_to_component(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        hoc_dir = circuit_dir / "hoc"
        hoc_dir.mkdir()
        pop_dir = circuit_dir / "pop_hoc"
        pop_dir.mkdir()

        hoc_file = tmp_path / "Generic.hoc"
        hoc_file.write_text("begintemplate Generic\nendtemplate Generic\n")

        config = {
            "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
            "networks": {
                "nodes": [
                    {
                        "populations": {
                            "pop_a": {
                                "biophysical_neuron_models_dir": str(pop_dir),
                            }
                        }
                    }
                ]
            },
        }

        # File not in population_map → goes to component dir
        _apply_emodel_overrides([hoc_file], {}, config, circuit_dir)
        assert (hoc_dir / "Generic.hoc").exists()
        assert not (pop_dir / "Generic.hoc").exists()
