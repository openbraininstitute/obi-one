"""Unit tests for the pure-logic helpers in the MEModel validation workflow.

These cover the parts of ``workflow.py`` that do not require a compiled NEURON
model or a live entitysdk client: calibration resolution, morphology selection,
and the mechanism compile/load error handling. The ``setup()`` body itself
(download, Cell construction, rheobase/Rin) is exercised end-to-end instead.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.schemas.memodel import DownloadedMEModel

from obi_one.scientific.validations.base import InvalidValidationContextError
from obi_one.scientific.validations.memodel.profiles import (
    DefaultMEModelValidationProfile,
    ThalamicMEModelValidationProfile,
)
from obi_one.scientific.validations.memodel.workflow import (
    _compile_mechanisms,
    _load_compiled_mechanisms,
    _resolve_holding_current,
    _select_morphology_path,
)


class TestResolveHoldingCurrent:
    def test_missing_defaults_to_zero_when_not_required(self):
        calibration = SimpleNamespace(holding_current=None)
        result = _resolve_holding_current(calibration, DefaultMEModelValidationProfile())
        assert result == pytest.approx(0.0)

    def test_missing_raises_when_profile_requires_it(self):
        calibration = SimpleNamespace(holding_current=None)
        with pytest.raises(InvalidValidationContextError, match="holding_current"):
            _resolve_holding_current(calibration, ThalamicMEModelValidationProfile())

    def test_returns_float_value(self):
        calibration = SimpleNamespace(holding_current=-0.03)
        result = _resolve_holding_current(calibration, DefaultMEModelValidationProfile())
        assert result == pytest.approx(-0.03)

    def test_non_numeric_raises(self):
        calibration = SimpleNamespace(holding_current="not-a-number")
        with pytest.raises(InvalidValidationContextError, match="finite number"):
            _resolve_holding_current(calibration, DefaultMEModelValidationProfile())

    def test_non_finite_raises(self):
        calibration = SimpleNamespace(holding_current=float("nan"))
        with pytest.raises(InvalidValidationContextError, match="finite number"):
            _resolve_holding_current(calibration, DefaultMEModelValidationProfile())


class TestSelectMorphologyPath:
    def _downloaded(self, morphology_paths):
        return DownloadedMEModel(
            hoc_path=Path("model.hoc"),
            mechanisms_dir=Path("mechanisms"),
            mechanism_files=[],
            morphology_paths=morphology_paths,
        )

    def test_prefers_asc(self):
        downloaded = self._downloaded([Path("m.swc"), Path("m.asc"), Path("m.h5")])
        assert _select_morphology_path(downloaded, "e1") == Path("m.asc")

    def test_falls_back_to_swc(self):
        downloaded = self._downloaded([Path("m.h5"), Path("m.swc")])
        assert _select_morphology_path(downloaded, "e1") == Path("m.swc")

    def test_raises_when_none_downloaded(self):
        downloaded = self._downloaded([])
        with pytest.raises(InvalidValidationContextError, match="No morphology"):
            _select_morphology_path(downloaded, "e1")

    def test_raises_when_no_loadable_format(self):
        downloaded = self._downloaded([Path("m.h5")])
        with pytest.raises(InvalidValidationContextError, match=r"No \.asc or \.swc"):
            _select_morphology_path(downloaded, "e1")


class TestCompileMechanisms:
    def test_missing_nrnivmodl_raises(self, tmp_path):
        with (
            patch(
                "obi_one.scientific.validations.memodel.workflow.subprocess.run",
                side_effect=FileNotFoundError,
            ),
            pytest.raises(InvalidValidationContextError, match="nrnivmodl"),
        ):
            _compile_mechanisms(tmp_path, tmp_path)

    def test_compile_failure_raises_with_output(self, tmp_path):
        error = subprocess.CalledProcessError(
            returncode=1, cmd="nrnivmodl", output="out", stderr="err"
        )
        with (
            patch(
                "obi_one.scientific.validations.memodel.workflow.subprocess.run",
                side_effect=error,
            ),
            pytest.raises(InvalidValidationContextError, match="exit code 1"),
        ):
            _compile_mechanisms(tmp_path, tmp_path)


class TestLoadCompiledMechanisms:
    def test_raises_when_no_library_produced(self, tmp_path):
        # Empty output dir: nrnivmodl "succeeded" but produced nothing.
        with pytest.raises(InvalidValidationContextError, match="no libnrnmech"):
            _load_compiled_mechanisms(tmp_path)

    def test_raises_when_library_cannot_load(self, tmp_path):
        lib_dir = tmp_path / "arm64"
        lib_dir.mkdir()
        (lib_dir / "libnrnmech.dylib").write_text("stub")
        fake_neuron = MagicMock()
        fake_neuron.h.nrn_load_dll.side_effect = RuntimeError("bad library")
        with (
            patch("obi_one.scientific.validations.memodel.workflow.neuron", fake_neuron),
            pytest.raises(InvalidValidationContextError, match="Could not load"),
        ):
            _load_compiled_mechanisms(tmp_path)

    def test_returns_loaded_library(self, tmp_path):
        lib_dir = tmp_path / "arm64"
        lib_dir.mkdir()
        lib = lib_dir / "libnrnmech.dylib"
        lib.write_text("stub")
        fake_neuron = MagicMock()
        with patch("obi_one.scientific.validations.memodel.workflow.neuron", fake_neuron):
            result = _load_compiled_mechanisms(tmp_path)
        assert result == lib
        fake_neuron.h.nrn_load_dll.assert_called_once_with(str(lib))
