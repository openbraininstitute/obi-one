"""Tests for the MEModel calibration + validation helpers."""

import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from entitysdk.types import ValidationStatus

from obi_one.scientific.library import memodel_calibration_validation as calibration_validation


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
