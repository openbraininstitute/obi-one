from pathlib import Path

import pytest
from entitysdk.types import ValidationStatus

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    locate_hoc,
    validation_status_from_results,
)


def _coord_root(tmp_path: Path) -> Path:
    """Minimal coord_root: sonata hoc (+ decoy files), arch dir, staged SWC."""
    sonata = tmp_path / "export_emodels_sonata"
    sonata.mkdir(parents=True)
    (sonata / "EM__emodel=test__seed=7.hoc").write_text("begintemplate T\nendtemplate T")
    (sonata / "morph.swc").write_text("1 1 0 0 0 1 -1")
    (sonata / "nodes.h5").write_bytes(b"h5")
    morph_dir = tmp_path / "morphologies"
    morph_dir.mkdir()
    (morph_dir / "morphology.swc").write_text("1 1 0 0 0 1 -1")
    arch = tmp_path / "arm64"
    arch.mkdir()
    (arch / "special").write_text("")
    return tmp_path


class TestLocateHoc:
    def test_returns_seed_matched_hoc(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        hoc = locate_hoc(coord_root, 7)
        assert hoc.name == "EM__emodel=test__seed=7.hoc"

    def test_missing_hoc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        (coord_root / "export_emodels_sonata" / "EM__emodel=test__seed=7.hoc").unlink()
        with pytest.raises(FileNotFoundError, match=r"No \.hoc file"):
            locate_hoc(coord_root, 7)

    def test_missing_mechanisms_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        (coord_root / "arm64" / "special").unlink()
        with pytest.raises(FileNotFoundError, match="compiled mechanisms"):
            locate_hoc(coord_root, 7)

    def test_seed_match_ignores_prefix_seed(self, tmp_path):
        """seed=7 must not match a file named seed=70."""
        coord_root = _coord_root(tmp_path)
        sonata = coord_root / "export_emodels_sonata"
        (sonata / "EM__emodel=test__seed=70.hoc").write_text("hoc")
        hoc = locate_hoc(coord_root, 7)
        assert hoc.name == "EM__emodel=test__seed=7.hoc"

    def test_ambiguous_hoc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        sonata = coord_root / "export_emodels_sonata"
        (sonata / "EM__emodel=test__seed=8.hoc").write_text("hoc")
        hoc = locate_hoc(coord_root, 7)
        assert "seed=7" in hoc.name

        (sonata / "EM__emodel=test__seed=9.hoc").write_text("hoc")
        (sonata / "EM__emodel=test__seed=7.hoc").unlink()
        with pytest.raises(RuntimeError, match="Ambiguous HOC"):
            locate_hoc(coord_root, 1)


class TestValidationStatusFromResults:
    def test_all_passed_is_done(self):
        results = {"t1": {"name": "A", "passed": True}, "t2": {"name": "B", "passed": True}}
        assert validation_status_from_results(results) == (ValidationStatus.done)

    def test_any_failure_stays_created(self):
        results = {"t1": {"name": "A", "passed": True}, "t2": {"name": "B", "passed": False}}
        assert validation_status_from_results(results) == (ValidationStatus.created)

    def test_empty_stays_created(self):
        assert validation_status_from_results({}) == (ValidationStatus.created)
