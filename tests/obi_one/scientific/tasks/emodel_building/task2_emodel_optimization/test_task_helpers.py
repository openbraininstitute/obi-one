import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from entitysdk.types import ValidationStatus

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    align_validation_protocols,
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

    def test_a_failed_test_stays_created(self):
        results = {"t1": {"name": "A", "passed": True}, "t2": {"name": "B", "passed": False}}
        assert validation_status_from_results(results) == (ValidationStatus.created)

    def test_thumbnail_and_skipped_checks_do_not_count(self):
        thumbnail = {"name": "thumbnail", "passed": True, "figures": ["t.png"]}
        skipped = {
            "name": "AisTest",
            "passed": True,
            "validation_details": "Validation skipped: Cell does not have an axon section.",
        }
        only_artifacts = {"thumbnail": thumbnail, "ais": skipped}
        assert validation_status_from_results(only_artifacts) == ValidationStatus.created
        failed = only_artifacts | {"spiking": {"name": "Spiking", "passed": False}}
        assert validation_status_from_results(failed) == ValidationStatus.created
        passed = only_artifacts | {"spiking": {"name": "Spiking", "passed": True}}
        assert validation_status_from_results(passed) == ValidationStatus.done

    def test_empty_stays_created(self):
        assert validation_status_from_results({}) == (ValidationStatus.created)

    def test_entries_without_verdict_stay_created(self):
        results = {"memodel_properties": {"holding_current": -0.1}}
        assert validation_status_from_results(results) == (ValidationStatus.created)


class TestAlignValidationProtocols:
    @staticmethod
    def _stage(tmp_path, flags):
        features = tmp_path / "config" / "features" / "em.json"
        features.parent.mkdir(parents=True)
        protocols = [{"name": name, "validation": flag} for name, flag in flags.items()]
        features.write_text(json.dumps({"efeatures": [], "protocols": protocols}))
        return features

    @staticmethod
    def _config(validation_protocols):
        return SimpleNamespace(
            initialize=SimpleNamespace(emodel="em"),
            optimization_settings=SimpleNamespace(validation_protocols=validation_protocols),
        )

    def test_empty_recipe_list_falls_back_to_extraction_flags(self, tmp_path):
        features = self._stage(tmp_path, {"IDrest_150": False, "IDrest_250": True})
        recipes = {"em": {"pipeline_settings": {"validation_protocols": []}}}
        result = align_validation_protocols(self._config(()), tmp_path, recipes)
        assert result == ["IDrest_250"]
        assert recipes["em"]["pipeline_settings"]["validation_protocols"] == ["IDrest_250"]
        flags = {p["name"]: p["validation"] for p in json.loads(features.read_text())["protocols"]}
        assert flags == {"IDrest_150": False, "IDrest_250": True}

    def test_configured_list_overrides_extraction_flags(self, tmp_path):
        features = self._stage(tmp_path, {"IDrest_150": False, "IDrest_250": True})
        recipes = {"em": {}}
        result = align_validation_protocols(self._config(("IDrest_150",)), tmp_path, recipes)
        assert result == ["IDrest_150"]
        assert recipes["em"]["pipeline_settings"]["validation_protocols"] == ["IDrest_150"]
        flags = {p["name"]: p["validation"] for p in json.loads(features.read_text())["protocols"]}
        assert flags == {"IDrest_150": True, "IDrest_250": False}
