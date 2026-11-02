"""Tests for upload-or-replace behavior in circuit asset helpers."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from obi_one.db_sdk.registration.circuit import assets as assets_module
from obi_one.db_sdk.registration.circuit.assets import COMPRESSED_CIRCUIT_FILENAME


def test_add_compressed_circuit_asset_uses_upload_or_replace(tmp_path):
    compressed = tmp_path / COMPRESSED_CIRCUIT_FILENAME
    compressed.write_bytes(b"gz")
    circuit = MagicMock()
    circuit.id = uuid4()
    client = MagicMock()

    with patch.object(
        assets_module, "_upload_or_replace_file", return_value=MagicMock(id=uuid4())
    ) as mock_up:
        assets_module.add_compressed_circuit_asset(client, compressed, circuit)

    mock_up.assert_called_once()


def test_add_connectivity_matrix_asset_uses_upload_or_replace(tmp_path):
    matrix_dir = tmp_path / "matrix"
    matrix_dir.mkdir()
    (matrix_dir / "matrix_config.json").write_text("{}")
    circuit = MagicMock()
    circuit.id = uuid4()
    client = MagicMock()

    with patch.object(
        assets_module, "_upload_or_replace_directory", return_value=MagicMock(id=uuid4())
    ) as mock_up:
        assets_module.add_connectivity_matrix_asset(client, matrix_dir, circuit)

    mock_up.assert_called_once()


def test_add_compressed_circuit_asset_rejects_wrong_filename(tmp_path):
    """A file that is not the canonical compressed-circuit archive is rejected."""
    compressed = tmp_path / "not_the_right_name.gz"
    compressed.write_bytes(b"gz")
    circuit = MagicMock()
    client = MagicMock()

    with (
        patch.object(assets_module, "_upload_or_replace_file") as mock_up,
        pytest.raises(ValueError, match="does not match"),
    ):
        assets_module.add_compressed_circuit_asset(client, compressed, circuit)

    mock_up.assert_not_called()


def test_add_connectivity_matrix_asset_rejects_missing_config(tmp_path):
    """A matrix directory without matrix_config.json is rejected before upload."""
    matrix_dir = tmp_path / "matrix"
    matrix_dir.mkdir()
    (matrix_dir / "connectivity_matrix.h5").write_text("data")
    circuit = MagicMock()
    client = MagicMock()

    with (
        patch.object(assets_module, "_upload_or_replace_directory") as mock_up,
        pytest.raises(ValueError, match="not found in"),
    ):
        assets_module.add_connectivity_matrix_asset(client, matrix_dir, circuit)

    mock_up.assert_not_called()
