"""Unit tests for circuit customization staging helpers."""

import json
import re
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import libsonata
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
    _validate_staged_id_mapping,
    stage_customized_circuit,
)

from tests.utils import CIRCUIT_DIR

TINY_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
EDGE_POP = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical"
NODE_POP = "S1nonbarrel_neurons"
STAGING_MODULE = "obi_one.utils.circuit_customization.staging"


def _circuit_config(cfg: dict, circuit_dir: Path) -> libsonata.CircuitConfig:
    """Build a libsonata config from a dict rooted at ``circuit_dir``."""
    networks = cfg.setdefault("networks", {})
    networks.setdefault("nodes", [])
    networks.setdefault("edges", [])
    return libsonata.CircuitConfig(json.dumps(cfg), str(circuit_dir))


# ---------------------------------------------------------------------------
# _resolve_hoc_dir
# ---------------------------------------------------------------------------


class TestResolveHocDir:
    def test_absolute_path(self, tmp_path):
        hoc_dir = tmp_path / "abs_hoc"
        circuit_dir = tmp_path / "circuit"
        config = _circuit_config(
            {"components": {"biophysical_neuron_models_dir": str(hoc_dir)}},
            circuit_dir,
        )
        result = _resolve_hoc_dir(config, circuit_dir)
        assert result == hoc_dir
        assert result.exists()

    def test_relative_path(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = _circuit_config(
            {"components": {"biophysical_neuron_models_dir": "models/hoc"}},
            circuit_dir,
        )
        result = _resolve_hoc_dir(config, circuit_dir)
        assert result == circuit_dir / "models" / "hoc"
        assert result.exists()

    def test_fallback_to_hoc(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = _circuit_config({"components": {}}, circuit_dir)
        result = _resolve_hoc_dir(config, circuit_dir)
        assert result == circuit_dir / "hoc"
        assert result.exists()


# ---------------------------------------------------------------------------
# _resolve_mod_dir
# ---------------------------------------------------------------------------


class TestResolveModDir:
    def test_absolute_path(self, tmp_path):
        mod_dir = tmp_path / "abs_mod"
        circuit_dir = tmp_path / "circuit"
        config = _circuit_config({"components": {"mechanisms_dir": str(mod_dir)}}, circuit_dir)
        result = _resolve_mod_dir(config, circuit_dir)
        assert result == mod_dir
        assert result.exists()

    def test_relative_path(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = _circuit_config({"components": {"mechanisms_dir": "mechanisms"}}, circuit_dir)
        result = _resolve_mod_dir(config, circuit_dir)
        assert result == circuit_dir / "mechanisms"
        assert result.exists()

    def test_fallback_to_mod(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config = _circuit_config({"components": {}}, circuit_dir)
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
    def test_collects_all_types(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        cfg = {
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "/path/to/nodes.h5",
                        "populations": {"pop_a": {"type": "virtual"}},
                    }
                ],
                "edges": [
                    {
                        "edges_file": "/path/to/edges.h5",
                        "populations": {"pop_a__pop_a__chemical": {"type": "chemical"}},
                    }
                ],
            },
            "node_sets_file": "/path/to/node_sets.json",
        }
        result = _network_file_names(_circuit_config(cfg, circuit_dir))
        assert result == {"nodes.h5", "edges.h5", "node_sets.json"}

    def test_empty_config(self, tmp_path):
        assert _network_file_names(_circuit_config({}, tmp_path / "circuit")) == set()

    def test_multiple_files(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        cfg = {
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "a.h5",
                        "populations": {"pop_a": {"type": "virtual"}},
                    },
                    {
                        "nodes_file": "b.h5",
                        "populations": {"pop_b": {"type": "virtual"}},
                    },
                ],
                "edges": [],
            },
        }
        result = _network_file_names(_circuit_config(cfg, circuit_dir))
        assert result == {"a.h5", "b.h5"}


# ---------------------------------------------------------------------------
# _apply_node_sets_override
# ---------------------------------------------------------------------------


class TestApplyNodeSetsOverride:
    def _staged_config(self, circuit_dir: Path, cfg: dict) -> Path:
        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))
        return config_path

    def test_replaces_referenced_file(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        (circuit_dir / "node_sets.json").write_text(json.dumps({"All": {}}))
        config_path = self._staged_config(circuit_dir, {"node_sets_file": "node_sets.json"})

        node_sets = tmp_path / "upload" / "node_sets.json"
        node_sets.parent.mkdir()
        node_sets.write_text(json.dumps({"All": {"population": "default"}}))

        _apply_node_sets_override(
            node_sets,
            circuit_dir,
            _circuit_config({"node_sets_file": "node_sets.json"}, circuit_dir),
            config_path,
            config_overridden=False,
        )

        assert json.loads((circuit_dir / "node_sets.json").read_text()) == {
            "All": {"population": "default"}
        }
        # No reference change was needed
        assert json.loads(config_path.read_text())["node_sets_file"] == "node_sets.json"

    def test_replaces_file_referenced_by_absolute_path(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        (circuit_dir / "nested").mkdir(parents=True)
        target = circuit_dir / "nested" / "node_sets.json"
        target.write_text(json.dumps({"All": {}}))
        config_path = self._staged_config(circuit_dir, {"node_sets_file": str(target)})

        node_sets = tmp_path / "node_sets.json"
        node_sets.write_text(json.dumps({"Layer1": {"layer": 1}}))

        _apply_node_sets_override(
            node_sets,
            circuit_dir,
            _circuit_config({"node_sets_file": str(target)}, circuit_dir),
            config_path,
            config_overridden=False,
        )

        assert json.loads(target.read_text()) == {"Layer1": {"layer": 1}}

    def test_replaces_symlinked_file(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        original = tmp_path / "parent_ns.json"
        original.write_text(json.dumps({"old": {}}))
        (circuit_dir / "ns.json").symlink_to(original)
        config_path = self._staged_config(circuit_dir, {"node_sets_file": "ns.json"})

        node_sets = tmp_path / "upload" / "ns.json"
        node_sets.parent.mkdir()
        node_sets.write_text(json.dumps({"new": {"population": "pop_a"}}))

        _apply_node_sets_override(
            node_sets,
            circuit_dir,
            _circuit_config({"node_sets_file": "ns.json"}, circuit_dir),
            config_path,
            config_overridden=False,
        )

        assert not (circuit_dir / "ns.json").is_symlink()
        assert json.loads((circuit_dir / "ns.json").read_text()) == {"new": {"population": "pop_a"}}
        # The parent's file behind the symlink is untouched
        assert json.loads(original.read_text()) == {"old": {}}

    def test_adds_reference_when_config_has_none(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config_path = self._staged_config(circuit_dir, {"networks": {}})

        node_sets = tmp_path / "my_node_sets.json"
        node_sets.write_text(json.dumps({"All": {}}))

        _apply_node_sets_override(
            node_sets,
            circuit_dir,
            _circuit_config({}, circuit_dir),
            config_path,
            config_overridden=False,
        )

        assert (circuit_dir / "my_node_sets.json").exists()
        assert json.loads(config_path.read_text())["node_sets_file"] == "my_node_sets.json"

    def test_repoints_reference_for_differently_named_upload(self, tmp_path):
        """The upload must take effect, not sit unreferenced next to the parent's file."""
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        (circuit_dir / "existing.json").write_text(json.dumps({"old": {}}))
        config_path = self._staged_config(circuit_dir, {"node_sets_file": "existing.json"})

        node_sets = tmp_path / "new_node_sets.json"
        node_sets.write_text(json.dumps({"All": {}}))

        _apply_node_sets_override(
            node_sets,
            circuit_dir,
            _circuit_config({"node_sets_file": "existing.json"}, circuit_dir),
            config_path,
            config_overridden=False,
        )

        assert json.loads(config_path.read_text())["node_sets_file"] == "new_node_sets.json"
        assert json.loads((circuit_dir / "new_node_sets.json").read_text()) == {"All": {}}

    def test_never_writes_through_the_staged_config_symlink(self, tmp_path):
        """Patching must not edit the parent circuit's own config on shared storage."""
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        parent_config = tmp_path / "parent_circuit_config.json"
        parent_config.write_text(json.dumps({"networks": {}}))
        config_path = circuit_dir / "circuit_config.json"
        config_path.symlink_to(parent_config)

        node_sets = tmp_path / "my_node_sets.json"
        node_sets.write_text(json.dumps({"All": {}}))

        _apply_node_sets_override(
            node_sets,
            circuit_dir,
            _circuit_config({}, circuit_dir),
            config_path,
            config_overridden=False,
        )

        assert json.loads(parent_config.read_text()) == {"networks": {}}
        assert json.loads(config_path.read_text())["node_sets_file"] == "my_node_sets.json"

    def test_mismatch_with_supplied_config_raises(self, tmp_path):
        """A user-supplied circuit_config is authoritative and is never rewritten."""
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        config_path = self._staged_config(circuit_dir, {"node_sets_file": "declared.json"})

        node_sets = tmp_path / "new_node_sets.json"
        node_sets.write_text(json.dumps({"All": {}}))

        with pytest.raises(ValueError, match=re.escape("new_node_sets.json")) as exc:
            _apply_node_sets_override(
                node_sets,
                circuit_dir,
                _circuit_config({"node_sets_file": "declared.json"}, circuit_dir),
                config_path,
                config_overridden=True,
            )

        assert "declared.json" in str(exc.value)
        assert not (circuit_dir / "new_node_sets.json").exists()
        assert json.loads(config_path.read_text())["node_sets_file"] == "declared.json"


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
            json.dumps(
                {
                    "networks": {
                        "nodes": [],
                        "edges": [
                            {
                                "edges_file": "new_edges.h5",
                                "populations": {"pop_a__pop_a__chemical": {"type": "chemical"}},
                            }
                        ],
                    }
                }
            )
        )

        parent_config = _circuit_config(
            {
                "networks": {
                    "nodes": [],
                    "edges": [
                        {
                            "edges_file": "old_edges.h5",
                            "populations": {"pop_a__pop_a__chemical": {"type": "chemical"}},
                        }
                    ],
                }
            },
            circuit_dir,
        )

        _remove_stale_network_files(circuit_dir, config_path, parent_config)
        assert not stale_link.exists()

    def test_removes_stale_plain_files(self, tmp_path):
        """Staging downloads real files when storage is not mounted — those go too."""
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        stale_file = circuit_dir / "old_nodes.h5"
        stale_file.write_bytes(b"data")

        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(
            json.dumps({"networks": {"nodes": [], "edges": []}}),
        )

        parent_config = _circuit_config(
            {
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "old_nodes.h5",
                            "populations": {"pop_a": {"type": "virtual"}},
                        }
                    ],
                    "edges": [],
                }
            },
            circuit_dir,
        )

        _remove_stale_network_files(circuit_dir, config_path, parent_config)
        assert not stale_file.exists()

    def test_keeps_files_still_referenced(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        kept = circuit_dir / "nodes.h5"
        kept.write_bytes(b"data")

        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "networks": {
                        "nodes": [
                            {
                                "nodes_file": "nodes.h5",
                                "populations": {"pop_a": {"type": "virtual"}},
                            }
                        ],
                        "edges": [],
                    }
                }
            )
        )

        parent_config = _circuit_config(
            {
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "nodes.h5",
                            "populations": {"pop_a": {"type": "virtual"}},
                        }
                    ],
                    "edges": [],
                }
            },
            circuit_dir,
        )

        _remove_stale_network_files(circuit_dir, config_path, parent_config)
        assert kept.exists()


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

        config = _circuit_config(
            {
                "networks": {
                    "nodes": [],
                    "edges": [
                        {
                            "edges_file": str(parent_edges),
                            "populations": {"pop_a__pop_a__chemical": {"type": "chemical"}},
                        }
                    ],
                }
            },
            circuit_dir,
        )

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

        config = _circuit_config(
            {
                "networks": {
                    "nodes": [],
                    "edges": [
                        {
                            "edges_file": str(circuit_dir / "edges.h5"),
                            "populations": {"pop_a__pop_a__chemical": {"type": "chemical"}},
                        }
                    ],
                }
            },
            circuit_dir,
        )

        with pytest.raises(ValueError, match="unknown_pop"):
            _apply_file_overrides([override], circuit_dir, config, component_type="edges")

    def test_adds_new_population_when_allowed(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        override = tmp_path / "virtual_nodes.h5"
        with h5py.File(override, "w") as f:
            f.create_group("nodes/new_virt")
            f["nodes/new_virt"].create_dataset("node_type_id", data=np.zeros(2, dtype=np.int32))

        config = _circuit_config(
            {
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "virtual_nodes.h5",
                            "populations": {"new_virt": {"type": "virtual"}},
                        }
                    ],
                    "edges": [],
                }
            },
            circuit_dir,
        )

        _apply_file_overrides(
            [override],
            circuit_dir,
            config,
            component_type="nodes",
            allow_new_populations=True,
        )

        target = circuit_dir / "virtual_nodes.h5"
        assert target.exists()
        with h5py.File(target, "r") as f:
            assert "new_virt" in f["nodes"]
            assert f["nodes/new_virt/node_type_id"].shape[0] == 2

    def test_new_population_without_config_entry_raises(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()

        override = tmp_path / "virtual_nodes.h5"
        with h5py.File(override, "w") as f:
            f.create_group("nodes/new_virt")

        config = _circuit_config({"networks": {"nodes": [], "edges": []}}, circuit_dir)

        with pytest.raises(ValueError, match="new_virt"):
            _apply_file_overrides(
                [override],
                circuit_dir,
                config,
                component_type="nodes",
                allow_new_populations=True,
            )

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

        config = _circuit_config(
            {
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": str(nodes_file),
                            "populations": {"pop_a": {"type": "virtual"}},
                        }
                    ],
                    "edges": [],
                }
            },
            circuit_dir,
        )

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

        config = _circuit_config(
            {
                "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "nodes.h5",
                            "populations": {"pop_a": {"type": "virtual"}},
                        }
                    ],
                    "edges": [],
                },
            },
            circuit_dir,
        )

        _apply_emodel_overrides([hoc_file], {}, config, circuit_dir)
        assert (hoc_dir / "MyCell.hoc").exists()

    def test_places_in_population_dir(self, tmp_path):
        circuit_dir = tmp_path / "circuit"
        circuit_dir.mkdir()
        pop_dir = circuit_dir / "pop_hoc"
        pop_dir.mkdir()

        hoc_file = tmp_path / "PopCell.hoc"
        hoc_file.write_text("begintemplate PopCell\nendtemplate PopCell\n")

        config = _circuit_config(
            {
                "components": {"biophysical_neuron_models_dir": str(circuit_dir / "hoc")},
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "nodes.h5",
                            "populations": {
                                "pop_a": {
                                    "type": "virtual",
                                    "biophysical_neuron_models_dir": str(pop_dir),
                                }
                            },
                        }
                    ],
                    "edges": [],
                },
            },
            circuit_dir,
        )

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

        config = _circuit_config(
            {
                "components": {"biophysical_neuron_models_dir": str(hoc_dir)},
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "nodes.h5",
                            "populations": {
                                "pop_a": {
                                    "type": "virtual",
                                    "biophysical_neuron_models_dir": str(pop_dir),
                                }
                            },
                        }
                    ],
                    "edges": [],
                },
            },
            circuit_dir,
        )

        # File not in population_map → goes to component dir
        _apply_emodel_overrides([hoc_file], {}, config, circuit_dir)
        assert (hoc_dir / "Generic.hoc").exists()
        assert not (pop_dir / "Generic.hoc").exists()


# ---------------------------------------------------------------------------
# stage_customized_circuit (mock entitysdk stage_circuit)
# ---------------------------------------------------------------------------


def _fake_stage_circuit(_client, *, model, output_dir: Path) -> Path:
    """Copy the tiny circuit into output_dir, simulating entitysdk staging."""
    del model
    dest = output_dir / "sonata_circuit"
    shutil.copytree(TINY_CIRCUIT, dest)
    return dest / "circuit_config.json"


def _write_edges_h5(path: Path, pop_name: str, n: int) -> None:
    with h5py.File(path, "w") as f:
        pop = f.create_group(f"edges/{pop_name}")
        pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
        pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
        pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))


def _write_nodes_h5(path: Path, pop_name: str, n: int) -> None:
    with h5py.File(path, "w") as f:
        pop = f.create_group(f"nodes/{pop_name}")
        pop.create_dataset("node_type_id", data=np.ones(n, dtype=np.int32))


class TestStageCustomizedCircuit:
    def test_applies_file_overrides_on_tiny_circuit(self, tmp_path):
        """Mock parent download; assert node/edge/hoc/mod/nodeset overrides land."""
        client = MagicMock()
        parent = MagicMock(name="parent_circuit")
        output_dir = tmp_path / "staged"

        edge_override = tmp_path / "edges_override.h5"
        _write_edges_h5(edge_override, EDGE_POP, n=7)

        node_override = tmp_path / "nodes_override.h5"
        _write_nodes_h5(node_override, NODE_POP, n=4)

        hoc_override = tmp_path / "cADpyr_L6BPC.hoc"
        hoc_override.write_text("begintemplate OverrideCell\nendtemplate OverrideCell\n")

        mod_override = tmp_path / "Ca_HVA2.mod"
        mod_override.write_text("NEURON {\n  SUFFIX OverrideCa\n}\n")

        node_sets_override = tmp_path / "node_sets.json"
        node_sets_override.write_text(json.dumps({"CustomSet": {"population": NODE_POP}}))

        with patch(
            f"{STAGING_MODULE}.stage_circuit", side_effect=_fake_stage_circuit
        ) as mock_stage:
            config_path = stage_customized_circuit(
                client,
                parent=parent,
                output_dir=output_dir,
                edge_overrides=[edge_override],
                node_overrides=[node_override],
                emodel_overrides=[hoc_override],
                emodel_population_map={"cADpyr_L6BPC.hoc": NODE_POP},
                mechanism_overrides=[mod_override],
                node_sets_override=node_sets_override,
            )

        mock_stage.assert_called_once()
        circuit_dir = config_path.parent

        edges_path = circuit_dir / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5"
        with h5py.File(edges_path, "r") as f:
            assert f[f"edges/{EDGE_POP}/source_node_id"].shape[0] == 7

        nodes_path = circuit_dir / "S1nonbarrel_neurons" / "nodes.h5"
        with h5py.File(nodes_path, "r") as f:
            assert f[f"nodes/{NODE_POP}/node_type_id"].shape[0] == 4

        assert (
            (circuit_dir / "emodels_hoc" / "cADpyr_L6BPC.hoc")
            .read_text()
            .startswith("begintemplate OverrideCell")
        )
        assert "OverrideCa" in (circuit_dir / "mod" / "Ca_HVA2.mod").read_text()
        assert json.loads((circuit_dir / "node_sets.json").read_text()) == {
            "CustomSet": {"population": NODE_POP}
        }

    def test_circuit_config_override_and_stale_symlink_cleanup(self, tmp_path):
        """Config override drops a uniquely named file; unused parent symlink is removed."""
        client = MagicMock()
        parent = MagicMock(name="parent_circuit")
        output_dir = tmp_path / "staged"

        def stage_synthetic(_client, *, model, output_dir: Path) -> Path:
            del model
            circuit_dir = output_dir / "sonata_circuit"
            circuit_dir.mkdir(parents=True)

            nodes = circuit_dir / "nodes_a.h5"
            _write_nodes_h5(nodes, "pop_a", n=2)
            keep_edges = circuit_dir / "keep_edges.h5"
            _write_edges_h5(keep_edges, "pop_a__pop_a", n=3)
            drop_edges = circuit_dir / "drop_edges.h5"
            _write_edges_h5(drop_edges, "virt__pop_a", n=1)

            # Mimic EFS staging: parent network file is a symlink
            parent_blob = tmp_path / "parent_drop_edges.h5"
            shutil.copy2(drop_edges, parent_blob)
            drop_edges.unlink()
            drop_edges.symlink_to(parent_blob)

            config = {
                "version": 2.3,
                "manifest": {"$BASE_DIR": str(circuit_dir)},
                "components": {},
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": "$BASE_DIR/nodes_a.h5",
                            "populations": {"pop_a": {"type": "virtual"}},
                        }
                    ],
                    "edges": [
                        {
                            "edges_file": "$BASE_DIR/keep_edges.h5",
                            "populations": {"pop_a__pop_a": {"type": "chemical"}},
                        },
                        {
                            "edges_file": "$BASE_DIR/drop_edges.h5",
                            "populations": {"virt__pop_a": {"type": "chemical"}},
                        },
                    ],
                },
            }
            config_path = circuit_dir / "circuit_config.json"
            config_path.write_text(json.dumps(config, indent=2))
            return config_path

        override_cfg = {
            "version": 2.3,
            "manifest": {"$BASE_DIR": "./"},
            "components": {},
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "$BASE_DIR/nodes_a.h5",
                        "populations": {"pop_a": {"type": "virtual"}},
                    }
                ],
                "edges": [
                    {
                        "edges_file": "$BASE_DIR/keep_edges.h5",
                        "populations": {"pop_a__pop_a": {"type": "chemical"}},
                    }
                ],
            },
        }
        config_override = tmp_path / "circuit_config.json"
        config_override.write_text(json.dumps(override_cfg, indent=2))

        with patch(f"{STAGING_MODULE}.stage_circuit", side_effect=stage_synthetic):
            config_path = stage_customized_circuit(
                client,
                parent=parent,
                output_dir=output_dir,
                circuit_config_override=config_override,
            )

        circuit_dir = config_path.parent
        assert (circuit_dir / "keep_edges.h5").exists()
        assert not (circuit_dir / "drop_edges.h5").exists()
        assert (
            json.loads(config_path.read_text())["networks"]["edges"]
            == override_cfg["networks"]["edges"]
        )


class TestValidateStagedIdMapping:
    def test_removes_stale_id_mapping(self, tmp_path):
        id_mapping = tmp_path / "id_mapping.json"
        id_mapping.write_text(json.dumps({"pop_a": {"new_id": [0, 99]}}))

        cfg = {
            "components": {"provenance": {"id_mapping": "id_mapping.json"}},
            "networks": {"nodes": []},
        }
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps(cfg))

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_circuit.nodes.__getitem__.return_value.size = 10

        with (
            patch(f"{STAGING_MODULE}.SnapCircuit", return_value=mock_circuit),
            patch(
                f"{STAGING_MODULE}.validate_id_mapping_files",
                return_value=["id_mapping.json is stale"],
            ) as mock_validate,
        ):
            _validate_staged_id_mapping(config_path)

        mock_validate.assert_called_once_with(config_path, mock_circuit)

    @patch(f"{STAGING_MODULE}.stage_circuit")
    def test_stage_customized_circuit_validates_id_mapping(self, mock_stage, tmp_path):
        circuit_dir = tmp_path / "staged"
        circuit_dir.mkdir()
        config_path = circuit_dir / "circuit_config.json"
        config_path.write_text(json.dumps({"networks": {"nodes": [], "edges": []}}))
        mock_stage.return_value = config_path

        with patch(f"{STAGING_MODULE}._validate_staged_id_mapping") as mock_validate:
            stage_customized_circuit(
                MagicMock(),
                parent=MagicMock(),
                output_dir=tmp_path / "out",
            )

        mock_validate.assert_called_once_with(config_path)
