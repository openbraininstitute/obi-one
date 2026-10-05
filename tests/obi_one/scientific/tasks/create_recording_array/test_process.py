"""Tests for create_recording_array/process.py."""

from unittest.mock import MagicMock, patch

import pytest

from obi_one.scientific.tasks.create_recording_array.process import (
    run_bluerecording_write_weights,
)


def test_run_bluerecording_write_weights_calls_subprocess_with_correct_args(tmp_path):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    circuit_config = tmp_path / "circuit_config.json"
    electrode_json = tmp_path / "electrodes.json"
    output_path = tmp_path / "weights.h5"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = run_bluerecording_write_weights(
            circuit_config,
            electrode_json,
            output_path,
            nrnmech_lib_path=str(tmp_path / "libnrnmech.so"),
        )

    assert result == output_path
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "bluerecording"
    assert call_args[1] == "write_weights"
    assert str(circuit_config) in call_args
    assert str(electrode_json) in call_args
    assert str(output_path) in call_args
    assert "NRNMECH_LIB_PATH" in mock_run.call_args[1]["env"]


def test_run_bluerecording_write_weights_logs_stdout_on_success(tmp_path):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "weights written"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        run_bluerecording_write_weights(
            tmp_path / "config.json",
            tmp_path / "electrodes.json",
            tmp_path / "weights.h5",
            nrnmech_lib_path=tmp_path / "libnrnmech.so",
        )


def test_run_bluerecording_write_weights_raises_on_failure(tmp_path):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Error: circuit not found"

    with (
        patch("subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="bluerecording write_weights failed"),
    ):
        run_bluerecording_write_weights(
            tmp_path / "config.json",
            tmp_path / "electrodes.json",
            tmp_path / "weights.h5",
            nrnmech_lib_path=str(tmp_path / "lib.so"),
        )
