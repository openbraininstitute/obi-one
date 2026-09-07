"""Tests for circuit customization endpoint — Layer 1 validations."""

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from app.endpoints.circuit_customization import (
    EdgeValidationError,
    HocValidationError,
    ModValidationError,
    NodeSetsValidationError,
    NodeValidationError,
    _extract_mod_mechanism_names,
    _validate_edges,
    _validate_hoc,
    _validate_hoc_mechanisms,
    _validate_mod,
    _validate_new_mod_not_synapse,
    _validate_node_sets,
    _validate_nodes,
    _validate_nodes_hoc_consistency,
)

# ---------------------------------------------------------------------------
# HOC validation (delegates to check_structure)
# ---------------------------------------------------------------------------


class TestValidateHoc:
    def test_valid_hoc(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text("begintemplate MyCell\nproc init() {}\nendtemplate MyCell\n")
        _validate_hoc([hoc])

    def test_wrong_extension(self, tmp_path):
        f = tmp_path / "cell.txt"
        f.write_text("begintemplate X\nendtemplate X\n")
        with pytest.raises(HocValidationError, match=r"expected \.hoc"):
            _validate_hoc([f])

    def test_missing_begintemplate(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text("proc init() {}\n")
        with pytest.raises(HocValidationError, match="begintemplate"):
            _validate_hoc([hoc])

    def test_missing_endtemplate(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text("begintemplate MyCell\nproc init() {}\n")
        with pytest.raises(HocValidationError, match="endtemplate"):
            _validate_hoc([hoc])


# ---------------------------------------------------------------------------
# MOD validation
# ---------------------------------------------------------------------------


class TestValidateMod:
    def test_valid_mod(self, tmp_path):
        mod = tmp_path / "NaTg.mod"
        mod.write_text("NEURON {\n  SUFFIX NaTg\n}\n")
        _validate_mod([mod])

    def test_wrong_extension(self, tmp_path):
        f = tmp_path / "NaTg.txt"
        f.write_text("NEURON {}\n")
        with pytest.raises(ModValidationError, match=r"expected \.mod"):
            _validate_mod([f])

    def test_missing_neuron_block(self, tmp_path):
        mod = tmp_path / "bad.mod"
        mod.write_text("PROCEDURE stuff() {}\n")
        with pytest.raises(ModValidationError, match="NEURON"):
            _validate_mod([mod])


# ---------------------------------------------------------------------------
# MOD mechanism extraction
# ---------------------------------------------------------------------------


class TestExtractModMechanismNames:
    def test_extracts_suffix(self, tmp_path):
        mod = tmp_path / "NaTg.mod"
        mod.write_text("NEURON {\n  SUFFIX NaTg\n}\nPROCEDURE ...\n")
        assert _extract_mod_mechanism_names([mod]) == {"NaTg"}

    def test_multiple_mods(self, tmp_path):
        m1 = tmp_path / "a.mod"
        m1.write_text("NEURON {\n  SUFFIX AlphaMech\n}\n")
        m2 = tmp_path / "b.mod"
        m2.write_text("NEURON {\n  SUFFIX BetaMech\n}\n")
        assert _extract_mod_mechanism_names([m1, m2]) == {"AlphaMech", "BetaMech"}

    def test_no_suffix(self, tmp_path):
        mod = tmp_path / "x.mod"
        mod.write_text("NEURON {\n  POINT_PROCESS Syn\n}\n")
        assert _extract_mod_mechanism_names([mod]) == set()


# ---------------------------------------------------------------------------
# HOC ↔ MOD cross-check
# ---------------------------------------------------------------------------


class TestValidateHocMechanisms:
    def test_valid_cross_check(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text("begintemplate X\n    insert NaTg\n    insert pas\nendtemplate X\n")
        mod = tmp_path / "NaTg.mod"
        mod.write_text("NEURON {\n  SUFFIX NaTg\n}\n")
        _validate_hoc_mechanisms([hoc], [mod])

    def test_missing_mechanism(self, tmp_path):
        hoc = tmp_path / "cell.hoc"
        hoc.write_text("begintemplate X\n    insert UnknownMech\nendtemplate X\n")
        with pytest.raises(HocValidationError, match="UnknownMech"):
            _validate_hoc_mechanisms([hoc], [])


# ---------------------------------------------------------------------------
# Edge validation
# ---------------------------------------------------------------------------


class TestValidateEdges:
    def _make_valid_edge_h5(self, path: Path, pop_name: str = "default"):
        with h5py.File(path, "w") as f:
            pop = f.create_group(f"edges/{pop_name}")
            n = 10
            pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))

    def test_valid_edges(self, tmp_path):
        edge = tmp_path / "edges.h5"
        self._make_valid_edge_h5(edge)
        _validate_edges([edge])

    def test_not_hdf5(self, tmp_path):
        edge = tmp_path / "edges.h5"
        edge.write_text("not hdf5")
        with pytest.raises(EdgeValidationError):
            _validate_edges([edge])


# ---------------------------------------------------------------------------
# Node validation
# ---------------------------------------------------------------------------


class TestValidateNodes:
    def _make_valid_node_h5(self, path: Path, pop_name: str = "default"):
        with h5py.File(path, "w") as f:
            grp = f.create_group(f"nodes/{pop_name}/0")
            n = 5
            grp.create_dataset(
                "model_template",
                data=np.array([b"hoc:MyCell"] * n),
            )
            f[f"nodes/{pop_name}"].create_dataset("node_type_id", data=np.zeros(n, dtype=np.int32))

    def test_valid_nodes(self, tmp_path):
        node = tmp_path / "nodes.h5"
        self._make_valid_node_h5(node)
        _validate_nodes([node])

    def test_not_hdf5(self, tmp_path):
        node = tmp_path / "nodes.h5"
        node.write_text("not hdf5")
        with pytest.raises(NodeValidationError):
            _validate_nodes([node])


# ---------------------------------------------------------------------------
# Node sets validation
# ---------------------------------------------------------------------------


class TestValidateNodeSets:
    def test_valid_node_sets(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"All": {"population": "default"}}))
        _validate_node_sets(ns)

    def test_invalid_json(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text("not json {{{")
        with pytest.raises(NodeSetsValidationError, match="invalid JSON"):
            _validate_node_sets(ns)

    def test_not_a_dict(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(NodeSetsValidationError, match="JSON object"):
            _validate_node_sets(ns)


# ---------------------------------------------------------------------------
# Nodes ↔ HOC consistency
# ---------------------------------------------------------------------------


class TestValidateNodesHocConsistency:
    def test_unused_hoc_raises(self, tmp_path):
        """An uploaded HOC file not referenced in nodes should raise."""
        node = tmp_path / "nodes.h5"
        with h5py.File(node, "w") as f:
            grp = f.create_group("nodes/pop/0")
            grp.create_dataset("model_template", data=[b"hoc:UsedCell"])
            f["nodes/pop"].create_dataset("node_type_id", data=[0])

        hoc = tmp_path / "UnusedCell.hoc"
        hoc.write_text("begintemplate UnusedCell\nendtemplate UnusedCell\n")
        with pytest.raises(ValueError, match="UnusedCell"):
            _validate_nodes_hoc_consistency([node], [hoc])

    def test_referenced_hoc_passes(self, tmp_path):
        node = tmp_path / "nodes.h5"
        with h5py.File(node, "w") as f:
            grp = f.create_group("nodes/pop/0")
            grp.create_dataset("model_template", data=[b"hoc:MyCell"])
            f["nodes/pop"].create_dataset("node_type_id", data=[0])

        hoc = tmp_path / "MyCell.hoc"
        hoc.write_text("begintemplate MyCell\nendtemplate MyCell\n")
        _validate_nodes_hoc_consistency([node], [hoc])


# ---------------------------------------------------------------------------
# New synapse MOD rejection
# ---------------------------------------------------------------------------


class TestValidateNewModNotSynapse:
    """Test _validate_new_mod_not_synapse: new MODs with NET_RECEIVE are rejected."""

    def test_existing_mod_with_net_receive_allowed(self, tmp_path):
        mod = tmp_path / "ExistingSyn.mod"
        mod.write_text("NEURON {\n  POINT_PROCESS ExistingSyn\n}\nNET_RECEIVE (w) {}\n")
        errors = _validate_new_mod_not_synapse([mod], parent_mechanism_names={"ExistingSyn"})
        assert errors == []

    def test_new_ion_channel_allowed(self, tmp_path):
        mod = tmp_path / "NewIon.mod"
        mod.write_text("NEURON {\n  SUFFIX NewIon\n}\nPROCEDURE rates() {}\n")
        errors = _validate_new_mod_not_synapse([mod], parent_mechanism_names=set())
        assert errors == []

    def test_new_synapse_rejected(self, tmp_path):
        mod = tmp_path / "NewSyn.mod"
        mod.write_text("NEURON {\n  POINT_PROCESS NewSyn\n}\nNET_RECEIVE (w) {}\n")
        errors = _validate_new_mod_not_synapse([mod], parent_mechanism_names=set())
        assert len(errors) == 1
        assert "NET_RECEIVE" in errors[0]
        assert "NewSyn" in errors[0]
