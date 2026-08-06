"""Tests for circuit validation task — unit-testable helpers."""

from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import pytest

from obi_one.scientific.tasks.circuit_validation.task import (
    _check_new_populations_not_biophysical,
    _collect_hoc_files,
    _find_stale_populations,
    _write_dynamics_to_h5,
    customization_parent_entity,
    is_circuit_customization,
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
# _collect_hoc_files
# ---------------------------------------------------------------------------


class TestCollectHocFiles:
    def test_collects_from_population_config(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "CellA.hoc").write_text("begintemplate CellA\nendtemplate CellA\n")
        (hoc_dir / "CellB.hoc").write_text("begintemplate CellB\nendtemplate CellB\n")
        (hoc_dir / "not_hoc.txt").write_text("ignored")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.config = {"biophysical_neuron_models_dir": str(hoc_dir)}
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        result = _collect_hoc_files(mock_circuit)
        assert len(result) == 2
        assert all(f.suffix == ".hoc" for f in result)

    def test_empty_when_no_dir(self):
        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["pop_a"]
        mock_pop = MagicMock()
        mock_pop.type = "biophysical"
        mock_pop.config = {}
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        assert _collect_hoc_files(mock_circuit) == []

    def test_skips_virtual_populations(self, tmp_path):
        hoc_dir = tmp_path / "hoc"
        hoc_dir.mkdir()
        (hoc_dir / "cell.hoc").write_text("x")

        mock_circuit = MagicMock()
        mock_circuit.nodes.population_names = ["virt"]
        mock_pop = MagicMock()
        mock_pop.type = "virtual"
        mock_pop.config = {"biophysical_neuron_models_dir": str(hoc_dir)}
        mock_circuit.nodes.__getitem__ = lambda _self, _k: mock_pop

        assert _collect_hoc_files(mock_circuit) == []


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
    """New populations must be virtual/point and match target_simulator."""

    @staticmethod
    def _snap_circuits(parent_pops: dict, child_pops: dict):
        """Build parent/child SnapCircuit mocks from {name: type} maps."""

        def _circuit(populations: dict):
            circuit = MagicMock()
            nodes_map = {}
            for name, pop_type in populations.items():
                pop = MagicMock()
                pop.type = pop_type
                nodes_map[name] = pop
            circuit.nodes.population_names = list(populations)
            circuit.nodes.__getitem__ = lambda _self, key, _n=nodes_map: _n[key]
            return circuit

        return _circuit(parent_pops), _circuit(child_pops)

    def test_new_virtual_allowed(self):
        parent_c, child_c = self._snap_circuits(
            {"pop_a": "biophysical"},
            {"pop_a": "biophysical", "new_virt": "virtual"},
        )
        errors = _check_new_populations_not_biophysical(child_c, parent_c)
        assert errors == []

    def test_new_biophysical_rejected(self):
        parent_c, child_c = self._snap_circuits(
            {"pop_a": "biophysical"},
            {"pop_a": "biophysical", "new_bio": "biophysical"},
        )
        errors = _check_new_populations_not_biophysical(child_c, parent_c)
        assert len(errors) == 1
        assert "new_bio" in errors[0]

    def test_new_point_neuron_allowed_for_neuron(self):
        parent_c, child_c = self._snap_circuits(
            {"pop_a": "biophysical"},
            {"pop_a": "biophysical", "new_pn": "point_neuron"},
        )
        errors = _check_new_populations_not_biophysical(
            child_c, parent_c, target_simulator="NEURON"
        )
        assert errors == []

    def test_brian2_point_rejected_on_neuron(self):
        parent_c, child_c = self._snap_circuits(
            {"pop_a": "biophysical"},
            {"pop_a": "biophysical", "new_brian": "brian2_point"},
        )
        errors = _check_new_populations_not_biophysical(
            child_c, parent_c, target_simulator="NEURON"
        )
        assert len(errors) == 1
        assert "new_brian" in errors[0]
        assert "brian2_point" in errors[0]
        assert "NEURON" in errors[0]

    def test_brian2_point_allowed_on_brian2(self):
        parent_c, child_c = self._snap_circuits(
            {"pop_a": "biophysical"},
            {"pop_a": "biophysical", "new_brian": "brian2_point"},
        )
        errors = _check_new_populations_not_biophysical(
            child_c, parent_c, target_simulator="Brian2"
        )
        assert errors == []

    def test_inait_point_allowed_on_learning_engine(self):
        parent_c, child_c = self._snap_circuits(
            {"pop_a": "biophysical"},
            {"pop_a": "biophysical", "new_le": "inait_point_neuron_lif"},
        )
        errors = _check_new_populations_not_biophysical(
            child_c, parent_c, target_simulator="LearningEngine"
        )
        assert errors == []


# ---------------------------------------------------------------------------
# is_circuit_customization / customization_parent_entity
# ---------------------------------------------------------------------------


class TestCircuitCustomizationHelpers:
    def test_is_customization_true(self):
        from entitysdk.types import DerivationType  # noqa: PLC0415

        circuit = MagicMock()
        deriv = MagicMock()
        deriv.derivation_type = DerivationType.circuit_customization
        circuit.generated_from_derivations = [deriv]
        assert is_circuit_customization(circuit) is True

    def test_is_customization_false_for_other_type(self):
        from entitysdk.types import DerivationType  # noqa: PLC0415

        circuit = MagicMock()
        deriv = MagicMock()
        deriv.derivation_type = DerivationType.circuit_extraction
        circuit.generated_from_derivations = [deriv]
        assert is_circuit_customization(circuit) is False

    def test_is_customization_false_when_no_derivations(self):
        circuit = MagicMock()
        circuit.generated_from_derivations = None
        assert is_circuit_customization(circuit) is False

    def test_customization_parent_entity(self):
        from entitysdk.types import DerivationType  # noqa: PLC0415

        parent = MagicMock()
        circuit = MagicMock()
        deriv = MagicMock()
        deriv.derivation_type = DerivationType.circuit_customization
        deriv.used = parent
        circuit.generated_from_derivations = [deriv]
        assert customization_parent_entity(circuit) is parent
