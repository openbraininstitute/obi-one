"""Tests for task2 MEModel calibration + validation helpers."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import entitysdk.downloaders.cell_morphology as dcm
import numpy as np
import pytest
from entitysdk.exception import IteratorResultError
from entitysdk.models import CellMorphology

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    calibration_validation,
    registration,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.registration import (
    RegisteredOptimizationOutputs,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    run_calibration_and_validation,
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


def _outputs() -> RegisteredOptimizationOutputs:
    return RegisteredOptimizationOutputs(
        task_result_id="tr-1",
        emodel_id="em-1",
        memodel_id=MEMODEL_ID,
        authorized_public=False,
        generated_ids=["tr-1", "em-1", "mem-1"],
    )


def _coord_root(tmp_path: Path, *, with_asc: bool = True) -> Path:
    """Minimal coord_root: sonata hoc (+ decoy morph files), arch dir, morphologies/."""
    sonata = tmp_path / "export_emodels_sonata"
    sonata.mkdir(parents=True)
    (sonata / "EM__emodel=test__seed=7.hoc").write_text("begintemplate T\nendtemplate T")
    # decoys: the SONATA morph copy is SWC and must NOT be picked; nodes.h5 neither
    (sonata / "morph.swc").write_text("1 1 0 0 0 1 -1")
    (sonata / "nodes.h5").write_bytes(b"h5")
    morph_dir = tmp_path / "morphologies"
    morph_dir.mkdir()
    if with_asc:
        (morph_dir / "morphology.asc").write_text("ASC morphology")
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


class TestDownloadAscMorphology:
    def test_downloads_asc(self, tmp_path, monkeypatch):
        morph = Mock()
        morph.entity.return_value = CellMorphology.model_construct(id="m-1")
        download = Mock(return_value=tmp_path / "morphologies" / "morphology.asc")
        monkeypatch.setattr(dcm, "download_morphology", download)

        result = calibration_validation.download_asc_morphology(Mock(), morph, tmp_path)

        assert result.name == "morphology.asc"
        assert download.call_args.args[3] == "asc"

    def test_missing_asc_raises(self, tmp_path, monkeypatch):
        morph = Mock()
        morph.entity.return_value = CellMorphology.model_construct(id="m-1")
        monkeypatch.setattr(
            dcm,
            "download_morphology",
            Mock(side_effect=IteratorResultError("no asset")),
        )

        with pytest.raises(ValueError, match="no ASC asset"):
            calibration_validation.download_asc_morphology(Mock(), morph, tmp_path)


class TestLocateHocAndMorphology:
    def test_returns_downloaded_asc_not_sonata_copy(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        asc = coord_root / "morphologies" / "morphology.asc"
        hoc, morph = calibration_validation.locate_hoc_and_morphology(coord_root, 7, asc)
        assert hoc.name == "EM__emodel=test__seed=7.hoc"
        # SWC copy inside the SONATA export and nodes.h5 are never picked
        assert morph == asc

    def test_missing_asc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path, with_asc=False)
        asc = coord_root / "morphologies" / "morphology.asc"
        with pytest.raises(FileNotFoundError, match="ASC morphology not found"):
            calibration_validation.locate_hoc_and_morphology(coord_root, 7, asc)

    def test_missing_hoc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        (coord_root / "export_emodels_sonata" / "EM__emodel=test__seed=7.hoc").unlink()
        asc = coord_root / "morphologies" / "morphology.asc"
        with pytest.raises(FileNotFoundError, match=r"No \.hoc file"):
            calibration_validation.locate_hoc_and_morphology(coord_root, 7, asc)

    def test_missing_mechanisms_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        (coord_root / "arm64" / "special").unlink()
        asc = coord_root / "morphologies" / "morphology.asc"
        with pytest.raises(FileNotFoundError, match="compiled mechanisms"):
            calibration_validation.locate_hoc_and_morphology(coord_root, 7, asc)

    def test_seed_match_ignores_prefix_seed(self, tmp_path):
        """seed=7 must not match a file named seed=70."""
        coord_root = _coord_root(tmp_path)
        sonata = coord_root / "export_emodels_sonata"
        (sonata / "EM__emodel=test__seed=70.hoc").write_text("hoc")
        asc = coord_root / "morphologies" / "morphology.asc"
        hoc, _morph = calibration_validation.locate_hoc_and_morphology(coord_root, 7, asc)
        assert hoc.name == "EM__emodel=test__seed=7.hoc"

    def test_ambiguous_hoc_raises(self, tmp_path):
        coord_root = _coord_root(tmp_path)
        sonata = coord_root / "export_emodels_sonata"
        (sonata / "EM__emodel=test__seed=8.hoc").write_text("hoc")
        asc = coord_root / "morphologies" / "morphology.asc"
        hoc, _morph = calibration_validation.locate_hoc_and_morphology(coord_root, 7, asc)
        assert "seed=7" in hoc.name

        (sonata / "EM__emodel=test__seed=9.hoc").write_text("hoc")
        (sonata / "EM__emodel=test__seed=7.hoc").unlink()
        with pytest.raises(RuntimeError, match="Ambiguous HOC"):
            calibration_validation.locate_hoc_and_morphology(coord_root, 1, asc)


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


class TestMarkMemodelValidated:
    def test_updates_validation_status(self):
        client = Mock()
        registration.mark_memodel_validated(client, MEMODEL_ID)
        kwargs = client.update_entity.call_args.kwargs
        assert kwargs["attrs_or_entity"]["validation_status"].value == "done"


class TestRunCalibrationAndValidation:
    def _patch(self, monkeypatch, **overrides):
        funcs = {
            "download_asc_morphology": Mock(return_value=Path("morphologies/morphology.asc")),
            "locate_hoc_and_morphology": Mock(return_value=(Path("hoc"), Path("morph.asc"))),
            "compute_calibration_in_subprocess": Mock(
                return_value={"holding_current": -0.1, "rheobase": 0.2, "rin": 50.0}
            ),
            "run_validations_in_subprocess": Mock(return_value={}),
        }
        funcs.update(overrides)
        for name, func in funcs.items():
            monkeypatch.setattr(calibration_validation, name, func)
        return funcs

    def _config(self):
        return SimpleNamespace(
            initialize=SimpleNamespace(emodel="test", morphology=Mock()),
            optimization_settings=SimpleNamespace(seed=7),
        )

    def test_happy_path(self, tmp_path, monkeypatch):
        (tmp_path / "final.json").write_text(
            json.dumps({"test": [{"holding_current": -0.05, "threshold_current": 0.15}]})
        )
        funcs = self._patch(monkeypatch)
        client = Mock()
        monkeypatch.setattr(registration, "register_calibration_result", Mock(return_value="cal-1"))
        reg_val = Mock(return_value=["vr-1", "vr-2"])
        monkeypatch.setattr(registration, "register_memodel_validation_results", reg_val)
        mark = Mock()
        monkeypatch.setattr(registration, "mark_memodel_validated", mark)
        upd = Mock()
        monkeypatch.setattr(registration, "update_activity_generated_ids", upd)

        run_calibration_and_validation(
            config=self._config(),
            coord_root=tmp_path,
            db_client=client,
            outputs=_outputs(),
            execution_activity_id="act-1",
        )

        # calibration seeds validation cell with calibrated values
        kwargs = funcs["run_validations_in_subprocess"].call_args.kwargs
        assert kwargs["holding_current"] == pytest.approx(-0.1)
        assert kwargs["threshold_current"] == pytest.approx(0.2)
        mark.assert_called_once_with(client, MEMODEL_ID)
        # generated_ids merge: old + calibration + validation ids
        upd.assert_called_once_with(
            client, "act-1", ["tr-1", "em-1", "mem-1", "cal-1", "vr-1", "vr-2"]
        )

    def test_failure_is_non_fatal(self, tmp_path, monkeypatch, caplog):
        funcs = self._patch(monkeypatch)
        funcs["locate_hoc_and_morphology"].side_effect = FileNotFoundError("no hoc")
        client = Mock()

        with caplog.at_level("WARNING"):
            run_calibration_and_validation(
                config=self._config(),
                coord_root=tmp_path,
                db_client=client,
                outputs=_outputs(),
                execution_activity_id=None,
            )

        assert "calibration/validation failed" in caplog.text
        client.update_entity.assert_not_called()
