"""Tests for circuit validation task — unit-testable helpers."""

from unittest.mock import MagicMock

from obi_one.scientific.tasks.circuit_validation.task import (
    _collect_hoc_files,
    _find_stale_populations,
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
