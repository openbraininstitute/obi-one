"""Tests for create_recording_array/process.py."""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock, patch

import pytest

from obi_one.scientific.tasks.create_recording_array.process import (
    compile_mechanisms,
    run_bluerecording_write_weights,
    write_electrode_json,
)


class TestCompileMechanisms:
    """Tests for compile_mechanisms (mocked subprocess)."""

    def test_returns_env_dict(self, tmp_path):
        """Returns parsed JSON env dict on success."""
        fake_env = {
            "NRNMECH_LIB_PATH": str(tmp_path / "libnrnmech.so"),
            "SPECIALS_PATH": str(tmp_path),
        }
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(fake_env)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = compile_mechanisms(tmp_path / "circuit_config.json", tmp_path / "out")

        assert result == fake_env
        assert (tmp_path / "out").exists()
        call_args = mock_run.call_args[0][0]
        assert "neurodamus-compile-mods" in call_args[0]
        assert "--with-internal-mods" not in call_args
        assert "--incflags=-DDISABLE_REPORTINGLIB" in call_args

    def test_raises_on_failure(self, tmp_path):
        """Raises RuntimeError when neurodamus-compile-mods fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "nrnivmodl not found"

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError, match="neurodamus-compile-mods failed"),
        ):
            compile_mechanisms(tmp_path / "circuit_config.json", tmp_path / "out")


class TestWriteElectrodeJson:
    """Tests for write_electrode_json."""

    def test_writes_correct_format(self, tmp_path):
        """Writes electrode positions in bluerecording JSON format."""

        class FakeBlock:
            def get_global_electrode_xyz_locations(self):
                return [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]

        electrode_locations = {"probe_a": FakeBlock()}
        output_path = tmp_path / "electrodes.json"

        result = write_electrode_json(electrode_locations, "PointSource", output_path)

        assert result == output_path
        data = json.loads(output_path.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "probe_a_electrode_0"
        assert math.isclose(data[0]["x"], 1.0)
        assert math.isclose(data[0]["y"], 2.0)
        assert math.isclose(data[0]["z"], 3.0)
        assert data[0]["type"] == "PointSource"
        assert data[1]["name"] == "probe_a_electrode_1"

    def test_multiple_blocks(self, tmp_path):
        """Handles multiple electrode location blocks."""

        class FakeBlockA:
            def get_global_electrode_xyz_locations(self):
                return [(0.0, 0.0, 0.0)]

        class FakeBlockB:
            def get_global_electrode_xyz_locations(self):
                return [(10.0, 10.0, 10.0)]

        electrode_locations = {"A": FakeBlockA(), "B": FakeBlockB()}
        output_path = tmp_path / "electrodes.json"

        write_electrode_json(electrode_locations, "LineSource", output_path)

        data = json.loads(output_path.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "A_electrode_0"
        assert data[1]["name"] == "B_electrode_0"
        assert data[1]["type"] == "LineSource"


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
