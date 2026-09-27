"""Tests for task2 MEModel calibration + validation helpers."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from entitysdk.types import ValidationStatus

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    calibration_validation,
    registration,
)


class FakeProcess:
    """Synchronous stand-in for ``multiprocessing.Process``."""

    def __init__(self, target, args):
        self._target = target
        self._args = args
        self.exitcode = None

    def start(self):
        pass

    def join(self):
        try:
            self._target(*self._args)
        except Exception:  # ruff: ignore[blind-except]
            self.exitcode = 1
        else:
            self.exitcode = 0


class FakeContext:
    def Process(self, target, args):
        return FakeProcess(target=target, args=args)


def _worker_ok(*args):
    Path(args[-1]).write_text(
        json.dumps({"holding_current": -0.1, "rheobase": 0.2, "rin": 50.0}), encoding="utf-8"
    )


def _worker_fail(*_args):
    msg = "boom"
    raise RuntimeError(msg)


def _worker_no_output(*_args):
    pass


def _fake_spawn(monkeypatch):
    monkeypatch.setattr(calibration_validation, "get_context", lambda _name: FakeContext())


MEMODEL_ID = "12345678-1234-5678-1234-567812345678"


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


class TestRunWorkerInSubprocess:
    def test_returns_worker_json(self, tmp_path, monkeypatch):
        _fake_spawn(monkeypatch)
        result = calibration_validation.run_worker_in_subprocess(
            _worker_ok, (str(tmp_path),), "Calibration"
        )
        assert result == {"holding_current": -0.1, "rheobase": 0.2, "rin": 50.0}

    def test_nonzero_exit_raises(self, tmp_path, monkeypatch):
        _fake_spawn(monkeypatch)
        with pytest.raises(RuntimeError, match="exit code 1"):
            calibration_validation.run_worker_in_subprocess(
                _worker_fail, (str(tmp_path),), "Calibration"
            )

    def test_missing_result_file_raises(self, tmp_path, monkeypatch):
        _fake_spawn(monkeypatch)
        with pytest.raises(RuntimeError, match="did not produce a result file"):
            calibration_validation.run_worker_in_subprocess(
                _worker_no_output, (str(tmp_path),), "Calibration"
            )


class TestSubprocessWrappers:
    def test_calibration_wrapper_passes_args(self, tmp_path, monkeypatch):
        _fake_spawn(monkeypatch)
        monkeypatch.setattr(calibration_validation, "calibration_worker", _worker_ok)
        result = calibration_validation.compute_calibration_in_subprocess(
            tmp_path, Path("hoc"), Path("morph"), holding_current=-0.05, threshold_current=0.1
        )
        assert result["rheobase"] == pytest.approx(0.2)

    def test_validation_wrapper_caps_n_processes(self, tmp_path, monkeypatch):
        runner = Mock(return_value={})
        monkeypatch.setattr(calibration_validation, "run_worker_in_subprocess", runner)
        monkeypatch.setattr(calibration_validation.os, "cpu_count", lambda: 3)

        calibration_validation.run_validations_in_subprocess(
            tmp_path, Path("hoc"), Path("morph"), "mem-1", output_dir=tmp_path / "figures"
        )

        assert runner.call_args.args[0] == calibration_validation.validation_worker
        worker_args = runner.call_args.args[1]
        assert worker_args[8] == 3  # n_processes position in the worker arg tuple


class TestJsonDefault:
    def test_numpy_and_path_objects(self, tmp_path):
        assert calibration_validation.json_default(np.float32(1.5)) == pytest.approx(1.5)
        flag = True
        assert calibration_validation.json_default(np.bool_(flag)) is True
        assert calibration_validation.json_default(np.array([1, 2])) == [1, 2]
        assert calibration_validation.json_default(tmp_path) == str(tmp_path)


class TestLocateHoc:
    def test_returns_seed_matched_hoc(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        hoc = calibration_validation.locate_hoc(coord_root, 7)
        assert hoc.name == "EM__emodel=test__seed=7.hoc"

    def test_missing_hoc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        (coord_root / "export_emodels_sonata" / "EM__emodel=test__seed=7.hoc").unlink()
        with pytest.raises(FileNotFoundError, match=r"No \.hoc file"):
            calibration_validation.locate_hoc(coord_root, 7)

    def test_missing_mechanisms_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        (coord_root / "arm64" / "special").unlink()
        with pytest.raises(FileNotFoundError, match="compiled mechanisms"):
            calibration_validation.locate_hoc(coord_root, 7)

    def test_seed_match_ignores_prefix_seed(self, tmp_path):
        """seed=7 must not match a file named seed=70."""
        coord_root = _coord_root(tmp_path)
        sonata = coord_root / "export_emodels_sonata"
        (sonata / "EM__emodel=test__seed=70.hoc").write_text("hoc")
        hoc = calibration_validation.locate_hoc(coord_root, 7)
        assert hoc.name == "EM__emodel=test__seed=7.hoc"

    def test_ambiguous_hoc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        sonata = coord_root / "export_emodels_sonata"
        (sonata / "EM__emodel=test__seed=8.hoc").write_text("hoc")
        hoc = calibration_validation.locate_hoc(coord_root, 7)
        assert "seed=7" in hoc.name

        (sonata / "EM__emodel=test__seed=9.hoc").write_text("hoc")
        (sonata / "EM__emodel=test__seed=7.hoc").unlink()
        with pytest.raises(RuntimeError, match="Ambiguous HOC"):
            calibration_validation.locate_hoc(coord_root, 1)


class TestComputeCalibrationAndValidation:
    def test_passes_calibrated_values_to_validation(self, tmp_path, monkeypatch):
        cal = Mock(return_value={"holding_current": -0.1, "rheobase": 0.2, "rin": 50.0})
        val = Mock(return_value={"spike_test": {"name": "SpikeTest", "passed": True}})
        monkeypatch.setattr(calibration_validation, "compute_calibration_in_subprocess", cal)
        monkeypatch.setattr(calibration_validation, "run_validations_in_subprocess", val)

        result = calibration_validation.compute_calibration_and_validation(
            tmp_path,
            Path("hoc"),
            tmp_path / "morphologies" / "morphology.swc",
            cell_name="test",
            holding_current=0.0,
            threshold_current=0.15,
            output_dir=tmp_path / "validation_figures",
        )

        assert result["calibration"]["rheobase"] == pytest.approx(0.2)
        assert result["validation"]["spike_test"]["passed"] is True
        val_kwargs = val.call_args.kwargs
        assert val_kwargs["holding_current"] == pytest.approx(-0.1)
        assert val_kwargs["threshold_current"] == pytest.approx(0.2)

    def test_failure_propagates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            calibration_validation,
            "compute_calibration_in_subprocess",
            Mock(side_effect=RuntimeError("subprocess crashed")),
        )
        with pytest.raises(RuntimeError, match="subprocess crashed"):
            calibration_validation.compute_calibration_and_validation(
                tmp_path,
                Path("hoc"),
                Path("morph.swc"),
                cell_name="test",
                holding_current=0.0,
                threshold_current=0.0,
                output_dir=tmp_path,
            )


class TestValidationStatusFromResults:
    def test_all_passed_is_done(self):
        results = {"t1": {"name": "A", "passed": True}, "t2": {"name": "B", "passed": True}}
        assert calibration_validation.validation_status_from_results(results) == (
            ValidationStatus.done
        )

    def test_any_failure_stays_created(self):
        results = {"t1": {"name": "A", "passed": True}, "t2": {"name": "B", "passed": False}}
        assert calibration_validation.validation_status_from_results(results) == (
            ValidationStatus.created
        )

    def test_empty_stays_created(self):
        assert calibration_validation.validation_status_from_results({}) == (
            ValidationStatus.created
        )


class TestRegisterCalibrationResult:
    def test_registers_with_field_mapping(self):
        client = Mock()
        client.search_entity.return_value.first.return_value = None
        registered = SimpleNamespace(id="cal-1")
        client.register_entity.return_value = registered

        result = registration.register_calibration_result(
            client,
            MEMODEL_ID,
            {"holding_current": -0.1, "rheobase": 0.2, "rin": 50.0},
            authorized_public=True,
        )

        assert result == "cal-1"
        entity = client.register_entity.call_args.kwargs["entity"]
        assert entity.holding_current == pytest.approx(-0.1)
        assert entity.threshold_current == pytest.approx(0.2)
        assert entity.rin == pytest.approx(50.0)
        assert str(entity.calibrated_entity_id) == MEMODEL_ID
        assert entity.authorized_public is True

    def test_skips_existing(self):
        client = Mock()
        client.search_entity.return_value.first.return_value = SimpleNamespace(id="cal-0")

        result = registration.register_calibration_result(
            client,
            MEMODEL_ID,
            {"holding_current": 0, "rheobase": 0},
            authorized_public=False,
        )

        assert result is None
        client.register_entity.assert_not_called()


class TestRegisterMemodelValidationResults:
    def test_registers_results_and_assets(self, tmp_path):
        figure = tmp_path / "fig.png"
        figure.write_bytes(b"png")
        validation_dict = {
            "memodel_properties": {"holding_current": -0.1},
            "spike_test": {
                "name": "SpikeTest",
                "passed": True,
                "figures": [str(figure), str(tmp_path / "missing.png")],
                "validation_details": "details",
            },
            "no_name_entry": {"passed": False},
        }
        client = Mock()
        client.search_entity.return_value.first.return_value = None
        client.register_entity.side_effect = lambda entity: SimpleNamespace(id=f"vr-{entity.name}")

        ids = registration.register_memodel_validation_results(
            client,
            MEMODEL_ID,
            validation_dict,
            authorized_public=False,
            details_dir=tmp_path / "details",
        )

        assert ids == ["vr-SpikeTest"]
        assert client.register_entity.call_count == 1
        entity = client.register_entity.call_args.kwargs["entity"]
        assert entity.name == "SpikeTest"
        assert entity.passed is True
        # figure upload + details upload; the missing figure is skipped
        assert client.upload_file.call_count == 2
        labels = {c.kwargs["asset_label"] for c in client.upload_file.call_args_list}
        assert labels == {"validation_result_figure", "validation_result_details"}

    def test_skips_existing_result(self, tmp_path):
        validation_dict = {"t": {"name": "SpikeTest", "passed": True}}
        client = Mock()
        client.search_entity.return_value.first.return_value = SimpleNamespace(id="vr-0")

        ids = registration.register_memodel_validation_results(
            client, MEMODEL_ID, validation_dict, authorized_public=False, details_dir=tmp_path
        )

        assert ids == []
        client.register_entity.assert_not_called()


class TestRegisterEmodelFigureValidationResults:
    def test_registers_recognized_figures_with_real_filename(self, tmp_path):
        figure = tmp_path / "emodel=test__seed=7__traces.pdf"
        figure.write_bytes(b"pdf")
        thumbnail = tmp_path / "emodel=test__seed=7__thumbnail.png"
        thumbnail.write_bytes(b"png")
        unknown = tmp_path / "emodel=test__seed=7__notes.pdf"
        unknown.write_bytes(b"pdf")
        client = Mock()
        client.register_entity.side_effect = lambda entity: SimpleNamespace(
            id=f"vr-{entity.name[:8]}"
        )

        ids = registration.register_emodel_figure_validation_results(
            client, MEMODEL_ID, [figure, thumbnail, unknown], authorized_public=False
        )

        assert len(ids) == 1  # thumbnail and unrecognised suffix are skipped
        entity = client.register_entity.call_args.kwargs["entity"]
        assert entity.name == figure.stem
        assert entity.passed is False
        assert str(entity.validated_entity_id) == MEMODEL_ID
        upload = client.upload_file.call_args.kwargs
        # real filename with extension → entitycore suffix check passes
        assert upload["file_path"] == figure
        assert upload["file_content_type"].value == "application/pdf"
        assert upload["asset_label"].value == "validation_result_figure"
