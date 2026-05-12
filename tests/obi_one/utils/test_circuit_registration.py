"""Tests for circuit registration utility functions."""

from datetime import datetime

import pytest

from obi_one.utils.circuit_registration import get_exp_date


# --- get_exp_date ---


def test_get_exp_date_none():
    """Test that None is returned when no date is provided."""
    assert get_exp_date({}) is None
    assert get_exp_date({"experiment_date": None}) is None


def test_get_exp_date_day_month_year():
    """Test parsing of dd.mm.YYYY format."""
    result = get_exp_date({"experiment_date": "27.03.2024"})
    assert result == datetime(2024, 3, 27)


def test_get_exp_date_month_year():
    """Test parsing of 'Month, YYYY' format."""
    result = get_exp_date({"experiment_date": "November, 2024"})
    assert result == datetime(2024, 11, 1)


def test_get_exp_date_unsupported_format():
    """Test that unsupported format raises."""
    with pytest.raises(ValueError, match="not supported"):
        get_exp_date({"experiment_date": "2024-03-27"})


def test_get_exp_date_invalid_string():
    """Test that invalid date string raises."""
    with pytest.raises(ValueError, match="not supported"):
        get_exp_date({"experiment_date": "not a date"})


from obi_one.utils.circuit_registration import (
    _check_file_path,
    _check_required_contents,
    _is_on_aws_s3,
)


# --- _is_on_aws_s3 ---


def test_is_on_aws_s3_true():
    """Test that S3 paths are detected."""
    assert _is_on_aws_s3("s3://openbluebrain/some/path") is True


def test_is_on_aws_s3_case_insensitive():
    """Test that detection is case-insensitive."""
    assert _is_on_aws_s3("S3://OpenBlueBrain/some/path") is True


def test_is_on_aws_s3_false():
    """Test that local paths are not detected as S3."""
    assert _is_on_aws_s3("/local/path/to/file") is False
    assert _is_on_aws_s3("relative/path") is False


def test_is_on_aws_s3_other_bucket():
    """Test that other S3 buckets are not detected."""
    assert _is_on_aws_s3("s3://some/path") is False


# --- _check_file_path ---


def test_check_file_path_empty():
    """Test that empty path raises."""
    with pytest.raises(ValueError, match="File path missing"):
        _check_file_path("")


def test_check_file_path_local_exists(tmp_path):
    """Test that existing local path passes."""
    f = tmp_path / "test.txt"
    f.write_text("hello")
    _check_file_path(str(f))  # Should not raise


def test_check_file_path_local_not_exists():
    """Test that non-existent local path raises."""
    with pytest.raises(ValueError, match="does not exist in local file system"):
        _check_file_path("/nonexistent/path/to/file.txt")


# --- _check_required_contents ---


def test_check_required_contents_empty_list(tmp_path):
    """Test that empty contents list passes without checking."""
    _check_required_contents(str(tmp_path), [], is_directory=True)


def test_check_required_contents_directory_valid(tmp_path):
    """Test that required files in a directory pass."""
    (tmp_path / "file_a.txt").write_text("a")
    (tmp_path / "file_b.txt").write_text("b")

    _check_required_contents(
        str(tmp_path), ["file_a.txt", "file_b.txt"], is_directory=True
    )


def test_check_required_contents_directory_missing(tmp_path):
    """Test that missing file in directory raises."""
    (tmp_path / "file_a.txt").write_text("a")

    with pytest.raises(ValueError, match="not found in"):
        _check_required_contents(
            str(tmp_path), ["file_a.txt", "missing.txt"], is_directory=True
        )


def test_check_required_contents_file_valid(tmp_path):
    """Test that file name matches for non-directory check."""
    f = tmp_path / "circuit.gz"
    f.write_text("data")

    _check_required_contents(str(f), ["circuit.gz"], is_directory=False)


def test_check_required_contents_file_mismatch(tmp_path):
    """Test that file name mismatch raises for non-directory check."""
    f = tmp_path / "other.gz"
    f.write_text("data")

    with pytest.raises(ValueError, match="does not match"):
        _check_required_contents(str(f), ["circuit.gz"], is_directory=False)


from obi_one.utils.circuit_registration import _check_matrix_folder


# --- _check_matrix_folder ---


def test_check_matrix_folder_valid(tmp_path):
    """Test that a valid matrix folder passes."""
    import json

    (tmp_path / "connectivity_matrix.h5").write_text("data")
    (tmp_path / "matrix_config.json").write_text(
        json.dumps({"pop1": {"single": {"path": "connectivity_matrix.h5"}}})
    )

    _check_matrix_folder(str(tmp_path))  # Should not raise


def test_check_matrix_folder_missing_config(tmp_path):
    """Test that missing matrix_config.json raises."""
    (tmp_path / "connectivity_matrix.h5").write_text("data")

    with pytest.raises(ValueError, match="matrix_config.json missing"):
        _check_matrix_folder(str(tmp_path))


def test_check_matrix_folder_missing_referenced_file(tmp_path):
    """Test that a referenced matrix file not found raises."""
    import json

    (tmp_path / "matrix_config.json").write_text(
        json.dumps({"pop1": {"single": {"path": "missing.h5"}}})
    )

    with pytest.raises(ValueError, match="referenced in config but not found"):
        _check_matrix_folder(str(tmp_path))


def test_check_matrix_folder_nested_structure(tmp_path):
    """Test that a valid matrix folder with nested paths passes."""
    import json

    (tmp_path / "pop1" / "single").mkdir(parents=True)
    (tmp_path / "pop1" / "single" / "connectivity_matrix.h5").write_text("data")
    (tmp_path / "matrix_config.json").write_text(
        json.dumps({"pop1": {"single": {"path": "pop1/single/connectivity_matrix.h5"}}})
    )

    _check_matrix_folder(str(tmp_path))  # Should not raise
