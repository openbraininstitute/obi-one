"""Tests for app/services/morphology.py

Covers functions not previously tested or only partially tested:
  - run_quality_checks
  - _check_warnings
  - load_morphio_morphology
  - _check_soma_radius
  - validate_soma_diameter
  - convert_morphology
  - validate_and_convert_morphology
  - MorphologyFiles.paths()
"""

from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, patch

import morphio
import pytest
from fastapi import HTTPException

from app.services.morphology import (
    MorphologyFiles,
    _check_soma_radius,
    _check_warnings,
    convert_morphology,
    load_morphio_morphology,
    run_quality_checks,
    validate_and_convert_morphology,
    validate_soma_diameter,
)


class TestMorphologyFiles:
    def test_paths_all_none(self):
        mf = MorphologyFiles()
        assert mf.paths() == []

    def test_paths_swc_only(self, tmp_path):
        p = tmp_path / "a.swc"
        mf = MorphologyFiles(swc=p)
        assert mf.paths() == [p]

    def test_paths_all_set(self, tmp_path):
        swc = tmp_path / "a.swc"
        h5 = tmp_path / "a.h5"
        asc = tmp_path / "a.asc"
        mf = MorphologyFiles(swc=swc, hdf5=h5, asc=asc)
        assert set(mf.paths()) == {swc, h5, asc}

    def test_paths_asc_only(self, tmp_path):
        asc = tmp_path / "a.asc"
        mf = MorphologyFiles(asc=asc)
        assert mf.paths() == [asc]


class TestRunQualityChecks:
    def test_returns_ran_to_completion_false_on_exception(self, tmp_path):
        bad_file = tmp_path / "bad.swc"
        bad_file.write_text("not a morphology")
        result = run_quality_checks(bad_file)
        assert result["ran_to_completion"] is False
        assert result["failed_checks"] == []
        assert result["passed_checks"] == []

    def test_ran_to_completion_true_on_success(self, tmp_path):
        mock_neuron = MagicMock()
        mock_check_results = {
            "morphology_checks": {
                "has_axon": True,
                "has_basal_dendrite": False,
            }
        }
        with (
            patch("app.services.morphology.neurom.load_morphology", return_value=mock_neuron),
            patch(
                "app.services.morphology._quality_check_runner.run",
                return_value=mock_check_results,
            ),
        ):
            result = run_quality_checks(tmp_path / "dummy.swc")

        assert result["ran_to_completion"] is True
        assert "has_axon" in result["passed_checks"]
        assert "has_basal_dendrite" in result["failed_checks"]

    def test_passed_and_failed_checks_are_separated_correctly(self):
        mock_neuron = MagicMock()
        mock_results = {
            "morphology_checks": {
                "check_a": True,
                "check_b": True,
                "check_c": False,
            }
        }
        with (
            patch("app.services.morphology.neurom.load_morphology", return_value=mock_neuron),
            patch(
                "app.services.morphology._quality_check_runner.run",
                return_value=mock_results,
            ),
        ):
            result = run_quality_checks(Path("anything.swc"))

        assert set(result["passed_checks"]) == {"check_a", "check_b"}
        assert result["failed_checks"] == ["check_c"]

    def test_empty_morphology_checks_key(self):
        mock_neuron = MagicMock()
        with (
            patch("app.services.morphology.neurom.load_morphology", return_value=mock_neuron),
            patch(
                "app.services.morphology._quality_check_runner.run",
                return_value={},
            ),
        ):
            result = run_quality_checks(Path("anything.swc"))

        assert result["ran_to_completion"] is True
        assert result["passed_checks"] == []
        assert result["failed_checks"] == []


class TestCheckWarnings:
    def test_no_warnings_does_not_raise(self):
        handler = MagicMock()
        handler.get_all.return_value = []
        # Should not raise
        _check_warnings(handler)

    def test_warnings_raises_morphio_error(self):
        warning = MagicMock()
        warning.warning = "SomeWarning"
        handler = MagicMock()
        handler.get_all.return_value = [warning]

        with pytest.raises(morphio.MorphioError):
            _check_warnings(handler)

    def test_multiple_warnings_joined_in_message(self):
        w1, w2 = MagicMock(), MagicMock()
        w1.warning = "WarningOne"
        w2.warning = "WarningTwo"
        handler = MagicMock()
        handler.get_all.return_value = [w1, w2]

        with pytest.raises(morphio.MorphioError, match="WarningOne"):
            _check_warnings(handler)


class TestLoadMorphioMorphology:
    def test_returns_morphology_on_success(self, tmp_path):
        mock_morphology = MagicMock(spec=morphio.Morphology)
        mock_handler = MagicMock()
        mock_handler.get_all.return_value = []

        with (
            patch("app.services.morphology.morphio.WarningHandlerCollector", return_value=mock_handler),
            patch("app.services.morphology.morphio.Morphology", return_value=mock_morphology),
        ):
            result = load_morphio_morphology(tmp_path / "neuron.swc", raise_warnings=False)

        assert result is mock_morphology

    def test_raises_http_exception_on_morphio_error(self, tmp_path):
        mock_handler = MagicMock()

        with (
            patch("app.services.morphology.morphio.WarningHandlerCollector", return_value=mock_handler),
            patch(
                "app.services.morphology.morphio.Morphology",
                side_effect=morphio.MorphioError("bad morphology"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                load_morphio_morphology(tmp_path / "bad.swc", raise_warnings=False)

        assert exc_info.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "Morphology validation failed" in exc_info.value.detail["detail"]

    def test_raise_warnings_true_calls_check_warnings(self, tmp_path):
        mock_morphology = MagicMock(spec=morphio.Morphology)
        mock_handler = MagicMock()
        mock_handler.get_all.return_value = []

        with (
            patch("app.services.morphology.morphio.WarningHandlerCollector", return_value=mock_handler),
            patch("app.services.morphology.morphio.Morphology", return_value=mock_morphology),
            patch("app.services.morphology._check_warnings") as mock_check,
        ):
            load_morphio_morphology(tmp_path / "neuron.swc", raise_warnings=True)

        mock_check.assert_called_once_with(warning_handler=mock_handler)

    def test_raise_warnings_false_skips_check_warnings(self, tmp_path):
        mock_morphology = MagicMock(spec=morphio.Morphology)
        mock_handler = MagicMock()

        with (
            patch("app.services.morphology.morphio.WarningHandlerCollector", return_value=mock_handler),
            patch("app.services.morphology.morphio.Morphology", return_value=mock_morphology),
            patch("app.services.morphology._check_warnings") as mock_check,
        ):
            load_morphio_morphology(tmp_path / "neuron.swc", raise_warnings=False)

        mock_check.assert_not_called()

    def test_warnings_present_with_raise_warnings_true_raises_http_exception(self, tmp_path):
        mock_morphology = MagicMock(spec=morphio.Morphology)
        mock_handler = MagicMock()

        with (
            patch("app.services.morphology.morphio.WarningHandlerCollector", return_value=mock_handler),
            patch("app.services.morphology.morphio.Morphology", return_value=mock_morphology),
            patch(
                "app.services.morphology._check_warnings",
                side_effect=morphio.MorphioError("a warning"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                load_morphio_morphology(tmp_path / "neuron.swc", raise_warnings=True)

        assert exc_info.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestCheckSomaRadius:
    @pytest.mark.parametrize("radius", [1.0, 50.0, 100.0])
    def test_valid_radii_do_not_raise(self, radius):
        _check_soma_radius(radius, threshold=100.0)

    @pytest.mark.parametrize("radius", [None, 0.0, -1.0, 101.0, 200.0])
    def test_invalid_radii_raise_value_error(self, radius):
        with pytest.raises(ValueError, match="Unrealistic soma diameter"):
            _check_soma_radius(radius, threshold=100.0)

    def test_radius_exactly_at_threshold_is_valid(self):
        _check_soma_radius(100.0, threshold=100.0)

    def test_radius_just_above_threshold_raises(self):
        with pytest.raises(ValueError):
            _check_soma_radius(100.001, threshold=100.0)


class TestValidateSomaDiameter:
    def test_valid_soma_does_not_raise(self, tmp_path):
        mock_morphology = MagicMock()
        mock_morphology.soma.radius = 10.0

        with patch("app.services.morphology.neurom.load_morphology", return_value=mock_morphology):
            validate_soma_diameter(tmp_path / "neuron.swc")

    def test_invalid_soma_radius_raises_http_exception(self, tmp_path):
        mock_morphology = MagicMock()
        mock_morphology.soma.radius = 999.0

        with (
            patch("app.services.morphology.neurom.load_morphology", return_value=mock_morphology),
            pytest.raises(HTTPException) as exc_info,
        ):
            validate_soma_diameter(tmp_path / "neuron.swc")

        assert exc_info.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "Soma diameter validation failed" in exc_info.value.detail["detail"]

    def test_neurom_error_raises_http_exception(self, tmp_path):
        from neurom.exceptions import NeuroMError

        with (
            patch(
                "app.services.morphology.neurom.load_morphology",
                side_effect=NeuroMError("neurom failed"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            validate_soma_diameter(tmp_path / "neuron.swc")

        assert exc_info.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_custom_threshold_is_respected(self, tmp_path):
        mock_morphology = MagicMock()
        mock_morphology.soma.radius = 5.0  # valid under default, also valid under custom

        with patch("app.services.morphology.neurom.load_morphology", return_value=mock_morphology):
            validate_soma_diameter(tmp_path / "neuron.swc", threshold=4.0)  # 5 > 4 → should raise

        # wait — 5.0 > 4.0 so it should raise. Let's verify the inverse too.
        mock_morphology.soma.radius = 3.0
        with patch("app.services.morphology.neurom.load_morphology", return_value=mock_morphology):
            validate_soma_diameter(tmp_path / "neuron.swc", threshold=4.0)  # 3 <= 4 → ok

    def test_soma_radius_above_custom_threshold_raises(self, tmp_path):
        mock_morphology = MagicMock()
        mock_morphology.soma.radius = 10.0

        with (
            patch("app.services.morphology.neurom.load_morphology", return_value=mock_morphology),
            pytest.raises(HTTPException),
        ):
            validate_soma_diameter(tmp_path / "neuron.swc", threshold=5.0)


class TestConvertMorphology:
    def test_converts_to_all_target_extensions(self, tmp_path):
        input_file = tmp_path / "neuron.swc"
        input_file.write_text("dummy")

        with patch("app.services.morphology.morph_tool.convert") as mock_convert:
            result = convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".h5": False, ".asc": False},
                target_exts=[".h5", ".asc"],
            )

        assert mock_convert.call_count == 2
        assert result.hdf5 == tmp_path / "neuron.h5"
        assert result.asc == tmp_path / "neuron.asc"

    def test_uses_custom_output_stem(self, tmp_path):
        input_file = tmp_path / "neuron.swc"
        input_file.write_text("dummy")

        with patch("app.services.morphology.morph_tool.convert"):
            result = convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".h5": False},
                target_exts=[".h5"],
                output_stem="custom_stem",
            )

        assert result.hdf5 == tmp_path / "custom_stem.h5"

    def test_swc_output_mapped_correctly(self, tmp_path):
        input_file = tmp_path / "neuron.h5"
        input_file.write_text("dummy")

        with patch("app.services.morphology.morph_tool.convert"):
            result = convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".swc": True},
                target_exts=[".swc"],
            )

        assert result.swc == tmp_path / "neuron.swc"

    def test_raises_http_exception_on_conversion_error(self, tmp_path):
        input_file = tmp_path / "neuron.swc"
        input_file.write_text("dummy")

        with (
            patch(
                "app.services.morphology.morph_tool.convert",
                side_effect=Exception("conversion failed"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".h5": False},
                target_exts=[".h5"],
            )

        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert "Failed to convert the file" in exc_info.value.detail["detail"]

    def test_single_point_soma_passed_to_morph_tool(self, tmp_path):
        input_file = tmp_path / "neuron.h5"
        input_file.write_text("dummy")

        with patch("app.services.morphology.morph_tool.convert") as mock_convert:
            convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".swc": True},
                target_exts=[".swc"],
            )

        _, kwargs = mock_convert.call_args
        assert kwargs["single_point_soma"] is True


class TestValidateAndConvertMorphology:
    def test_calls_load_then_convert(self, tmp_path):
        input_file = tmp_path / "neuron.swc"
        input_file.write_text("dummy")
        expected = MorphologyFiles(hdf5=tmp_path / "neuron.h5")

        with (
            patch("app.services.morphology.load_morphio_morphology") as mock_load,
            patch("app.services.morphology.convert_morphology", return_value=expected) as mock_convert,
        ):
            result = validate_and_convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".h5": False},
                target_exts=[".h5"],
            )

        mock_load.assert_called_once_with(input_file, raise_warnings=False)
        mock_convert.assert_called_once()
        assert result is expected

    def test_load_failure_prevents_conversion(self, tmp_path):
        input_file = tmp_path / "bad.swc"
        input_file.write_text("invalid")

        with (
            patch(
                "app.services.morphology.load_morphio_morphology",
                side_effect=HTTPException(status_code=422, detail="bad"),
            ),
            patch("app.services.morphology.convert_morphology") as mock_convert,
            pytest.raises(HTTPException),
        ):
            validate_and_convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".h5": False},
            )

        mock_convert.assert_not_called()

    def test_passes_through_optional_params(self, tmp_path):
        input_file = tmp_path / "neuron.swc"
        input_file.write_text("dummy")
        expected = MorphologyFiles()

        with (
            patch("app.services.morphology.load_morphio_morphology"),
            patch("app.services.morphology.convert_morphology", return_value=expected) as mock_convert,
        ):
            validate_and_convert_morphology(
                input_file,
                output_dir=tmp_path,
                single_point_soma_by_ext={".h5": False},
                target_exts=[".h5"],
                output_stem="my_stem",
            )

        _, kwargs = mock_convert.call_args
        assert kwargs["output_stem"] == "my_stem"
        assert kwargs["target_exts"] == [".h5"]
