"""Additional unit tests for circuit_customization — edge cases and uncovered paths."""

import json

import h5py
import numpy as np
import pytest
from fastapi import HTTPException

from app.endpoints.circuit_customization import (
    EdgeValidationError,
    NodeSetsValidationError,
    _collect_templates_from_group,
    _parse_population_manifest,
    _run_cross_validations,
    _validate_edges,
    _validate_mod,
    _validate_node_sets,
    _validate_nodes_hoc_consistency,
)

# ---------------------------------------------------------------------------
# _parse_population_manifest
# ---------------------------------------------------------------------------


class TestParsePopulationManifest:
    def test_none_returns_empty(self):
        assert _parse_population_manifest(None) == {}

    def test_empty_string_returns_empty(self):
        assert _parse_population_manifest("") == {}

    def test_valid_manifest(self):
        result = _parse_population_manifest('{"CellA.hoc": "pop_a", "CellB.hoc": "pop_b"}')
        assert result == {"CellA.hoc": "pop_a", "CellB.hoc": "pop_b"}

    def test_invalid_json_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_population_manifest("not json {")
        assert exc_info.value.status_code == 422
        assert "invalid JSON" in exc_info.value.detail

    def test_non_dict_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_population_manifest("[1, 2, 3]")
        assert exc_info.value.status_code == 422

    def test_non_string_values_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_population_manifest('{"file.hoc": 123}')
        assert exc_info.value.status_code == 422

    def test_non_string_keys_raises(self):
        # JSON keys are always strings, but values might not be
        with pytest.raises(HTTPException) as exc_info:
            _parse_population_manifest('{"file.hoc": null}')
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# _collect_templates_from_group — string vs enumerated datasets
# ---------------------------------------------------------------------------


class TestCollectTemplatesFromGroup:
    def test_string_dataset(self, tmp_path):
        h5_file = tmp_path / "nodes.h5"
        with h5py.File(h5_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("model_template", data=[b"hoc:CellA", b"hoc:CellB"])

        templates = set()
        with h5py.File(h5_file, "r") as f:
            group = f["nodes/pop_a/0"]
            _collect_templates_from_group(f, group, "pop_a", templates)

        assert templates == {"hoc:CellA", "hoc:CellB"}

    def test_enumerated_dataset_with_library(self, tmp_path):
        h5_file = tmp_path / "nodes.h5"
        with h5py.File(h5_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            # Enumerated (uint) dataset
            grp.create_dataset("model_template", data=np.array([0, 1, 0], dtype=np.uint32))
            # Library reference
            f.create_dataset(
                "nodes/pop_a/0/@library/model_template",
                data=[b"hoc:CellX", b"hoc:CellY"],
            )

        templates = set()
        with h5py.File(h5_file, "r") as f:
            group = f["nodes/pop_a/0"]
            _collect_templates_from_group(f, group, "pop_a", templates)

        assert templates == {"hoc:CellX", "hoc:CellY"}

    def test_no_model_template(self, tmp_path):
        h5_file = tmp_path / "nodes.h5"
        with h5py.File(h5_file, "w") as f:
            grp = f.create_group("nodes/pop_a/0")
            grp.create_dataset("morphology", data=[b"morph1"])

        templates = set()
        with h5py.File(h5_file, "r") as f:
            group = f["nodes/pop_a/0"]
            _collect_templates_from_group(f, group, "pop_a", templates)

        assert templates == set()


# ---------------------------------------------------------------------------
# _validate_node_sets — additional edge cases
# ---------------------------------------------------------------------------


class TestValidateNodeSetsExtra:
    def test_population_as_list(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"pop_set": {"population": ["pop_a", "pop_b"]}}))
        _validate_node_sets(ns)  # should not raise

    def test_node_id_as_int(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"single": {"node_id": 42}}))
        _validate_node_sets(ns)  # should not raise

    def test_node_id_as_list(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"multi": {"node_id": [1, 2, 3]}}))
        _validate_node_sets(ns)  # should not raise

    def test_operator_values_allowed(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"regex_set": {"$regex": "L[23].*"}}))
        _validate_node_sets(ns)  # should not raise

    def test_invalid_population_value(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"bad": {"population": 123}}))
        with pytest.raises(NodeSetsValidationError, match="population"):
            _validate_node_sets(ns)

    def test_invalid_node_id_value(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"bad": {"node_id": "not_int"}}))
        with pytest.raises(NodeSetsValidationError, match="node_id"):
            _validate_node_sets(ns)

    def test_invalid_attr_filter_value(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"bad": {"mtype": {"nested": "dict_not_allowed"}}}))
        with pytest.raises(NodeSetsValidationError, match="attribute filter"):
            _validate_node_sets(ns)

    def test_compound_expression(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"compound": [{"mtype": "L2_PC"}, "other_set"]}))
        _validate_node_sets(ns)  # should not raise

    def test_invalid_compound_item(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"bad_compound": [123]}))
        with pytest.raises(NodeSetsValidationError, match="compound"):
            _validate_node_sets(ns)

    def test_scalar_expression_raises(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"bad": 42}))
        with pytest.raises(NodeSetsValidationError, match="must be a dict or list"):
            _validate_node_sets(ns)


# ---------------------------------------------------------------------------
# _validate_edges — NaN detection
# ---------------------------------------------------------------------------


class TestValidateEdgesNaN:
    def test_nan_in_float_column(self, tmp_path):
        edge_file = tmp_path / "edges.h5"
        with h5py.File(edge_file, "w") as f:
            pop = f.create_group("edges/pop_a")
            n = 5
            pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))
            # Float column with NaN
            data = np.array([1.0, 2.0, float("nan"), 4.0, 5.0], dtype=np.float32)
            pop.create_dataset("conductance", data=data)

        with pytest.raises(EdgeValidationError, match="NaN or Inf"):
            _validate_edges([edge_file])

    def test_inf_in_float_column(self, tmp_path):
        edge_file = tmp_path / "edges.h5"
        with h5py.File(edge_file, "w") as f:
            pop = f.create_group("edges/pop_a")
            n = 5
            pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))
            data = np.array([1.0, float("inf"), 3.0, 4.0, 5.0], dtype=np.float32)
            pop.create_dataset("weight", data=data)

        with pytest.raises(EdgeValidationError, match="NaN or Inf"):
            _validate_edges([edge_file])

    def test_missing_edges_group(self, tmp_path):
        edge_file = tmp_path / "edges.h5"
        with h5py.File(edge_file, "w") as f:
            f.create_group("nodes")  # wrong group

        with pytest.raises(EdgeValidationError, match="missing 'edges' group"):
            _validate_edges([edge_file])

    def test_missing_required_field(self, tmp_path):
        edge_file = tmp_path / "edges.h5"
        with h5py.File(edge_file, "w") as f:
            pop = f.create_group("edges/pop_a")
            pop.create_dataset("source_node_id", data=np.arange(5, dtype=np.int64))
            # Missing target_node_id and edge_type_id

        with pytest.raises(EdgeValidationError, match="missing"):
            _validate_edges([edge_file])


# ---------------------------------------------------------------------------
# _validate_mod — valid multiple MODs
# ---------------------------------------------------------------------------


class TestValidateModExtra:
    def test_multiple_valid_mods(self, tmp_path):
        m1 = tmp_path / "NaTg.mod"
        m1.write_text("NEURON {\n  SUFFIX NaTg\n}\n")
        m2 = tmp_path / "Kv3_1.mod"
        m2.write_text("NEURON {\n  SUFFIX Kv3_1\n}\n")
        _validate_mod([m1, m2])


# ---------------------------------------------------------------------------
# _validate_nodes_hoc_consistency — empty templates
# ---------------------------------------------------------------------------


class TestNodesHocConsistencyExtra:
    def test_no_templates_in_nodes(self, tmp_path):
        """If no model_template is found in nodes, function returns early (no error)."""
        node = tmp_path / "nodes.h5"
        with h5py.File(node, "w") as f:
            grp = f.create_group("nodes/pop/0")
            grp.create_dataset("morphology", data=[b"morph1"])
            f["nodes/pop"].create_dataset("node_type_id", data=[0])

        hoc = tmp_path / "SomeCell.hoc"
        hoc.write_text("begintemplate SomeCell\nendtemplate SomeCell\n")
        # Should not raise since no templates are found in nodes
        _validate_nodes_hoc_consistency([node], [hoc])

    def test_template_without_colon_is_ignored(self, tmp_path):
        """Templates that don't have ':' in them are skipped for HOC matching."""
        node = tmp_path / "nodes.h5"
        with h5py.File(node, "w") as f:
            grp = f.create_group("nodes/pop/0")
            grp.create_dataset("model_template", data=[b"NoColonTemplate"])
            f["nodes/pop"].create_dataset("node_type_id", data=[0])

        hoc = tmp_path / "SomeCell.hoc"
        hoc.write_text("begintemplate SomeCell\nendtemplate SomeCell\n")
        # node_template_stems will be empty (no ':' in template)
        # So uploaded_hoc_stems - empty = {"SomeCell"} → raises
        with pytest.raises(ValueError, match="SomeCell"):
            _validate_nodes_hoc_consistency([node], [hoc])


# ---------------------------------------------------------------------------
# _run_cross_validations
# ---------------------------------------------------------------------------


class TestRunCrossValidations:
    def test_empty_paths(self):
        errors = _run_cross_validations(
            hoc_paths=[], mod_paths=[], node_paths=[], parent_mechanism_names=None
        )
        assert errors == []

    def test_new_synapse_mod_rejected(self, tmp_path):
        mod = tmp_path / "NewSyn.mod"
        mod.write_text("NEURON {\n  POINT_PROCESS NewSyn\n}\nNET_RECEIVE (w) {}\n")
        errors = _run_cross_validations(
            hoc_paths=[], mod_paths=[mod], node_paths=[], parent_mechanism_names=set()
        )
        assert len(errors) == 1
        assert "NET_RECEIVE" in errors[0]
