"""Tests for SONATA circuit validation utilities."""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from unittest.mock import patch

import pytest

from obi_one.utils.circuit_validation import run_validation

from tests.utils import CIRCUIT_DIR


class TestRunValidation:
    def test_valid_circuit(self):
        """Validation passes for a valid circuit."""
        circuit_path = str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json")
        fatals, warnings = run_validation(circuit_path)
        assert fatals == []
        assert isinstance(warnings, list)

    def test_invalid_path(self, tmp_path):
        """Validation raises for a non-existent circuit."""
        with pytest.raises((FileNotFoundError, ValueError)):
            run_validation(str(tmp_path / "nonexistent" / "circuit_config.json"))

    def test_invalid_circuit(self):
        """Validation raises for a circuit with missing data files."""
        circuit_path = str(
            CIRCUIT_DIR / "N_10__top_nodes_dim6__config_only" / "circuit_config.json"
        )
        with pytest.raises(ValueError, match="Circuit validation error"):
            run_validation(circuit_path)

    def test_returns_errors_without_raising(self):
        """raise_on_error=False returns fatal errors instead of raising."""
        circuit_path = str(
            CIRCUIT_DIR / "N_10__top_nodes_dim6__config_only" / "circuit_config.json"
        )
        fatals, warnings = run_validation(circuit_path, raise_on_error=False)
        assert fatals
        assert isinstance(warnings, list)

    @patch("obi_one.utils.circuit_validation.snap_circuit_validation.validate")
    def test_returns_warnings_without_fatals(self, mock_validate, tmp_path):
        """Warnings-only SNAP results should not raise and should be returned."""
        from bluepysnap.circuit_validation import (  # ruff: ignore[import-outside-top-level]
            BluepySnapValidationError,
        )

        mock_validate.return_value = {BluepySnapValidationError.warning("partial circuit warning")}
        circuit_path = tmp_path / "circuit_config.json"

        fatals, warnings = run_validation(circuit_path, raise_on_error=True)

        assert fatals == []
        assert any("partial circuit warning" in warning for warning in warnings)
        mock_validate.assert_called_once()
        assert mock_validate.call_args.kwargs["only_errors"] is False
        assert mock_validate.call_args.kwargs["ignore_edge_properties"]

    @patch("obi_one.utils.circuit_validation.snap_circuit_validation.validate", return_value=[])
    def test_clean_validation_logs_no_errors(self, mock_validate):
        """A clean SNAP result returns empty fatal and warning lists."""
        fatals, warnings = run_validation("circuit_config.json")

        assert fatals == []
        assert warnings == []
        mock_validate.assert_called_once()


def test_simulation_execution_does_not_import_circuit_validation():
    """Normal simulation imports must not load the validation dependency."""
    script = """
import sys
import obi_one.scientific.tasks.simulation_execution
assert "bluepysnap.circuit_validation" not in sys.modules
assert "obi_one.utils.circuit_validation" not in sys.modules
"""
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script], check=True
    )
