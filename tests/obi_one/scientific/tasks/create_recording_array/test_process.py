"""Tests for create_recording_array/process.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from obi_one.scientific.tasks.create_recording_array.process import (
    run_bluerecording_write_weights,
)


class TestRunBluerecordingWriteWeights:
    """Tests for run_bluerecording_write_weights (mocked subprocess)."""

    def test_calls_subprocess_with_correct_args(self, tmp_path):
        """Calls bluerecording CLI with correct arguments and env."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        circuit_config = tmp_path / "circuit_config.json"
        electrode_json = tmp_path / "electrodes.json"
        output_path = tmp_path / "weights.h5"
        env = {"NRNMECH_LIB_PATH": str(tmp_path / "libnrnmech.so")}

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = run_bluerecording_write_weights(
                circuit_config, electrode_json, output_path, env=env
            )

        assert result == output_path
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "bluerecording"
        assert call_args[1] == "write_weights"
        assert str(circuit_config) in call_args
        assert str(electrode_json) in call_args
        assert str(output_path) in call_args
        # env should include NRNMECH_LIB_PATH
        call_kwargs = mock_run.call_args[1]
        assert "NRNMECH_LIB_PATH" in call_kwargs["env"]

    def test_raises_on_failure(self, tmp_path):
        """Raises RuntimeError when bluerecording fails."""
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
                env={"NRNMECH_LIB_PATH": str(tmp_path / "lib.so")},
            )
