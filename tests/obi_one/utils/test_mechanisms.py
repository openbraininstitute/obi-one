"""Tests for obi_one.utils.mechanisms."""

from unittest.mock import patch

import pytest

from obi_one.utils.mechanisms import clean_compiled_mechanisms, compile_mechanisms


@patch("obi_one.utils.mechanisms.subprocess.run")
def test_compile_mechanisms(mock_run, tmp_path):
    """Test that nrnivmodl is invoked with the expected arguments."""
    mech_dir = tmp_path / "mod"
    mech_dir.mkdir()

    compile_mechanisms(mech_dir)

    mock_run.assert_called_once_with(
        [
            "nrnivmodl",
            "-incflags",
            "-DDISABLE_REPORTINGLIB",
            str(mech_dir),
        ],
        check=True,
    )


def test_clean_compiled_mechanisms_removes_existing_dirs(tmp_path, monkeypatch):
    """Test that compiled mechanism directories are removed when present."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x86_64").mkdir()
    (tmp_path / "arm64").mkdir()
    (tmp_path / "x86_64" / "libnrnmech.so").write_text("dummy")

    clean_compiled_mechanisms()

    assert not (tmp_path / "x86_64").exists()
    assert not (tmp_path / "arm64").exists()


def test_clean_compiled_mechanisms_noop_when_missing(tmp_path, monkeypatch):
    """Test that clean_compiled_mechanisms does not raise when dirs are absent."""
    monkeypatch.chdir(tmp_path)

    clean_compiled_mechanisms()


@patch("obi_one.utils.mechanisms.subprocess.run")
def test_compile_mechanisms_propagates_subprocess_error(mock_run, tmp_path):
    """Test that subprocess failures are propagated."""
    mock_run.side_effect = OSError("nrnivmodl not found")

    with pytest.raises(OSError, match="nrnivmodl not found"):
        compile_mechanisms(tmp_path)
