"""Additional unit tests for circuit_customization — edge cases and uncovered paths."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import pytest
from entitysdk.types import DerivationType
from fastapi import HTTPException

from app.endpoints.circuit_customization import (
    EdgeValidationError,
    NodeSetsValidationError,
    ParentCircuitContext,
    _collect_uploaded_model_templates,
    _get_parent_context,
    _parse_population_manifest,
    _run_cross_validations,
    _stage_and_register,
    _validate_edges,
    _validate_mod,
    _validate_node_sets,
    _validate_nodes_hoc_consistency,
)

from tests.utils import CIRCUIT_DIR

TINY_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
CUSTOMIZATION_MODULE = "app.endpoints.circuit_customization"

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
# _collect_uploaded_model_templates — string vs enumerated storage
# ---------------------------------------------------------------------------


def _write_nodes(
    path: Path, *, templates: list[bytes] | None = None, library: bool = False
) -> Path:
    """Write a minimal SONATA nodes file, optionally with model_template values."""
    with h5py.File(path, "w") as f:
        pop = f.create_group("nodes/pop_a")
        grp = f.create_group("nodes/pop_a/0")
        n = len(templates) if templates else 1
        pop.create_dataset("node_type_id", data=np.full(n, -1, dtype=np.int32))
        grp.create_dataset("morphology", data=[b"morph"] * n)
        if templates is None:
            return path
        if library:
            values = sorted(set(templates))
            grp.create_dataset(
                "model_template",
                data=np.array([values.index(t) for t in templates], dtype=np.uint32),
            )
            grp.create_dataset("@library/model_template", data=values)
        else:
            grp.create_dataset("model_template", data=templates)
    return path


class TestCollectUploadedModelTemplates:
    def test_string_dataset(self, tmp_path):
        node = _write_nodes(tmp_path / "nodes.h5", templates=[b"hoc:CellA", b"hoc:CellB"])
        assert _collect_uploaded_model_templates([node]) == {"hoc:CellA", "hoc:CellB"}

    def test_enumerated_dataset_with_library(self, tmp_path):
        node = _write_nodes(
            tmp_path / "nodes.h5",
            templates=[b"hoc:CellX", b"hoc:CellY", b"hoc:CellX"],
            library=True,
        )
        assert _collect_uploaded_model_templates([node]) == {"hoc:CellX", "hoc:CellY"}

    def test_no_model_template(self, tmp_path):
        node = _write_nodes(tmp_path / "nodes.h5")
        assert _collect_uploaded_model_templates([node]) == set()

    def test_unreadable_file_is_skipped(self, tmp_path):
        broken = tmp_path / "broken.h5"
        broken.write_bytes(b"not hdf5")
        good = _write_nodes(tmp_path / "nodes.h5", templates=[b"hoc:CellA"])
        assert _collect_uploaded_model_templates([broken, good]) == {"hoc:CellA"}

    def test_reads_tiny_circuit_nodes(self):
        node = TINY_CIRCUIT / "S1nonbarrel_neurons" / "nodes.h5"
        templates = _collect_uploaded_model_templates([node])
        assert templates
        assert all(t.startswith("hoc:") for t in templates)


# ---------------------------------------------------------------------------
# _validate_node_sets — additional edge cases
# ---------------------------------------------------------------------------


class TestValidateNodeSetsExtra:
    def test_population_as_list(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"pop_set": {"population": ["pop_a", "pop_b"]}}))
        _validate_node_sets(ns)  # should not raise

    def test_node_id_as_int_rejected(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"single": {"node_id": 42}}))
        with pytest.raises(NodeSetsValidationError, match="node_id"):
            _validate_node_sets(ns)

    def test_node_id_as_list(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"multi": {"node_id": [1, 2, 3]}}))
        _validate_node_sets(ns)  # should not raise

    def test_bool_attribute_filter_allowed(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"exc": {"synapse_class": True}}))
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
        ns.write_text(json.dumps({"compound": ["other_set", "layer2"]}))
        _validate_node_sets(ns)  # should not raise

    def test_compound_dict_item_rejected(self, tmp_path):
        ns = tmp_path / "node_sets.json"
        ns.write_text(json.dumps({"compound": [{"mtype": "L2_PC"}, "other_set"]}))
        with pytest.raises(NodeSetsValidationError, match="compound"):
            _validate_node_sets(ns)

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
# _validate_edges — structural checks
# ---------------------------------------------------------------------------


class TestValidateEdgesStructure:
    def test_accepts_real_sonata_layout(self):
        """Properties live under /edges/<pop>/0 — that layout must pass."""
        edge_file = TINY_CIRCUIT / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5"
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

    def _nodes_with_template(self, path: Path, template: bytes) -> Path:
        with h5py.File(path, "w") as f:
            grp = f.create_group("nodes/pop/0")
            grp.create_dataset("model_template", data=[template])
            f["nodes/pop"].create_dataset("node_type_id", data=[0])
        return path

    def test_hoc_referenced_only_by_parent_nodes_is_accepted(self, tmp_path):
        """A HOC replacement used by a population the customization does not touch."""
        node = self._nodes_with_template(tmp_path / "nodes.h5", b"hoc:UploadedCell")

        uploaded = tmp_path / "UploadedCell.hoc"
        uploaded.write_text("begintemplate UploadedCell\nendtemplate UploadedCell\n")
        parent_only = tmp_path / "ParentCell.hoc"
        parent_only.write_text("begintemplate ParentCell\nendtemplate ParentCell\n")

        parent = ParentCircuitContext(
            mechanism_names=set(),
            hoc_stems={"ParentCell", "UploadedCell"},
            model_template_stems={"ParentCell", "UploadedCell"},
        )
        _validate_nodes_hoc_consistency([node], [uploaded, parent_only], parent)

    def test_hoc_referenced_nowhere_raises(self, tmp_path):
        node = self._nodes_with_template(tmp_path / "nodes.h5", b"hoc:UploadedCell")

        uploaded = tmp_path / "UploadedCell.hoc"
        uploaded.write_text("begintemplate UploadedCell\nendtemplate UploadedCell\n")
        orphan = tmp_path / "Orphan.hoc"
        orphan.write_text("begintemplate Orphan\nendtemplate Orphan\n")

        parent = ParentCircuitContext(
            mechanism_names=set(),
            hoc_stems={"UploadedCell"},
            model_template_stems={"UploadedCell"},
        )
        with pytest.raises(ValueError, match="Orphan"):
            _validate_nodes_hoc_consistency([node], [uploaded, orphan], parent)

    def test_template_without_matching_hoc_raises(self, tmp_path):
        """Check 1: an uploaded node references a HOC that is nowhere to be found."""
        node = self._nodes_with_template(tmp_path / "nodes.h5", b"hoc:GhostCell")

        uploaded = tmp_path / "UploadedCell.hoc"
        uploaded.write_text("begintemplate UploadedCell\nendtemplate UploadedCell\n")

        parent = ParentCircuitContext(
            mechanism_names=set(),
            hoc_stems={"ParentCell"},
            model_template_stems={"ParentCell", "UploadedCell"},
        )
        with pytest.raises(ValueError, match="GhostCell"):
            _validate_nodes_hoc_consistency([node], [uploaded], parent)

    def test_template_check_skipped_without_parent_hoc_stems(self, tmp_path):
        """An unreadable parent must not turn into a spurious rejection."""
        node = self._nodes_with_template(tmp_path / "nodes.h5", b"hoc:GhostCell")

        uploaded = tmp_path / "GhostCell.hoc"
        uploaded.write_text("begintemplate GhostCell\nendtemplate GhostCell\n")
        other = tmp_path / "OtherCell.hoc"
        other.write_text("begintemplate OtherCell\nendtemplate OtherCell\n")

        empty_parent = ParentCircuitContext(
            mechanism_names=set(), hoc_stems=set(), model_template_stems={"OtherCell"}
        )
        _validate_nodes_hoc_consistency([node], [uploaded, other], empty_parent)


# ---------------------------------------------------------------------------
# _run_cross_validations
# ---------------------------------------------------------------------------


class TestRunCrossValidations:
    def test_empty_paths(self):
        errors = _run_cross_validations(hoc_paths=[], mod_paths=[], node_paths=[], parent=None)
        assert errors == []

    def test_new_synapse_mod_rejected(self, tmp_path):
        mod = tmp_path / "NewSyn.mod"
        mod.write_text("NEURON {\n  POINT_PROCESS NewSyn\n}\nNET_RECEIVE (w) {}\n")
        errors = _run_cross_validations(
            hoc_paths=[],
            mod_paths=[mod],
            node_paths=[],
            parent=ParentCircuitContext(
                mechanism_names=set(), hoc_stems=set(), model_template_stems=set()
            ),
        )
        assert len(errors) == 1
        assert "NET_RECEIVE" in errors[0]


# ---------------------------------------------------------------------------
# _get_parent_context
# ---------------------------------------------------------------------------


def _fake_stage_circuit(_client, *, model, output_dir: Path) -> Path:
    del model
    dest = output_dir / "sonata_circuit"
    shutil.copytree(TINY_CIRCUIT, dest)
    return dest / "circuit_config.json"


class TestGetParentContext:
    def test_reads_tiny_circuit_in_one_staging_pass(self):
        """Stage the repo tiny circuit (mocked entitysdk) and read its facts via SNAP."""
        expected_mods = {p.stem for p in (TINY_CIRCUIT / "mod").glob("*.mod")}
        expected_hocs = {p.stem for p in (TINY_CIRCUIT / "emodels_hoc").glob("*.hoc")}
        assert expected_mods  # sanity: fixture has mechanisms
        assert expected_hocs  # sanity: fixture has e-models

        with patch(
            f"{CUSTOMIZATION_MODULE}.stage_circuit",
            side_effect=_fake_stage_circuit,
        ) as mock_stage:
            context = _get_parent_context(MagicMock(), MagicMock(name="parent"))

        mock_stage.assert_called_once()
        assert context.mechanism_names == expected_mods
        # Spot-check a few well-known mechanisms from the N_10 fixture
        assert {"NaTg", "Ca_HVA2", "ProbAMPANMDA_EMS", "ProbGABAAB_EMS"} <= context.mechanism_names
        assert context.hoc_stems == expected_hocs
        # Every template the circuit references is backed by one of those HOC files
        assert context.model_template_stems
        assert context.model_template_stems <= context.hoc_stems

    def test_staging_failure_yields_empty_context(self):
        with patch(
            f"{CUSTOMIZATION_MODULE}.stage_circuit",
            side_effect=OSError("no assets"),
        ):
            context = _get_parent_context(MagicMock(), MagicMock(name="parent"))

        assert context.mechanism_names == set()
        assert context.hoc_stems == set()
        assert context.model_template_stems == set()


# ---------------------------------------------------------------------------
# _stage_and_register
# ---------------------------------------------------------------------------


def _make_parent() -> MagicMock:
    parent = MagicMock(name="parent")
    parent.build_category = "computational_model"
    parent.target_simulator = "NEURON"
    return parent


def _call_stage_and_register(db_client, parent, tmp_path: Path):
    return _stage_and_register(
        db_client=db_client,
        parent=parent,
        name="customized",
        description="a customized circuit",
        tmp=tmp_path,
        edge_paths=[],
        hoc_paths=[],
        mod_paths=[],
        node_paths=[],
        node_sets_path=None,
        cfg_path=None,
        pop_map={},
    )


class TestStageAndRegister:
    def test_delegates_registration_to_register_circuit(self, tmp_path):
        """Staging output is handed to register_circuit with parent-derived metadata."""
        parent = _make_parent()
        registered = MagicMock(name="registered")
        merged_config = tmp_path / "staged" / "circuit_config.json"

        with (
            patch(
                "app.endpoints.circuit_customization.stage_customized_circuit",
                return_value=merged_config,
            ) as mock_stage,
            patch(
                "app.endpoints.circuit_customization.register_circuit",
                return_value=registered,
            ) as mock_register,
        ):
            result = _call_stage_and_register(MagicMock(), parent, tmp_path)

        assert result is registered
        assert mock_stage.call_args.kwargs["output_dir"] == tmp_path / "staged"

        kwargs = mock_register.call_args.kwargs
        assert kwargs["circuit_path"] == merged_config
        assert kwargs["parent"] is parent
        assert kwargs["derivation_type"] == DerivationType.circuit_customization
        assert kwargs["build_category"] == parent.build_category
        assert kwargs["target_simulator"] == parent.target_simulator
        assert kwargs["brain_region"] is parent.brain_region
        assert kwargs["subject"] is parent.subject
        assert kwargs["license"] is parent.license
        assert kwargs["lifecycle_status"] == "draft"
        assert kwargs["skip_validation"] is True
        # The staged tree is symlinks into the parent's storage: the compressed
        # archive is produced later by the post-validation asset job.
        assert kwargs["include_compressed"] is False

    def test_staging_error_becomes_422(self, tmp_path):
        with (
            patch(
                "app.endpoints.circuit_customization.stage_customized_circuit",
                side_effect=ValueError("bad population"),
            ),
            patch("app.endpoints.circuit_customization.register_circuit") as mock_register,
            pytest.raises(HTTPException) as exc,
        ):
            _call_stage_and_register(MagicMock(), _make_parent(), tmp_path)

        assert exc.value.status_code == 422
        assert "bad population" in str(exc.value.detail)
        mock_register.assert_not_called()

    def test_registration_error_becomes_422(self, tmp_path):
        with (
            patch(
                "app.endpoints.circuit_customization.stage_customized_circuit",
                return_value=tmp_path / "staged" / "circuit_config.json",
            ),
            patch(
                "app.endpoints.circuit_customization.register_circuit",
                side_effect=ValueError("species mismatch"),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            _call_stage_and_register(MagicMock(), _make_parent(), tmp_path)

        assert exc.value.status_code == 422
        assert "species mismatch" in str(exc.value.detail)

    def test_missing_entity_becomes_500(self, tmp_path):
        with (
            patch(
                "app.endpoints.circuit_customization.stage_customized_circuit",
                return_value=tmp_path / "staged" / "circuit_config.json",
            ),
            patch(
                "app.endpoints.circuit_customization.register_circuit",
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            _call_stage_and_register(MagicMock(), _make_parent(), tmp_path)

        assert exc.value.status_code == 500
