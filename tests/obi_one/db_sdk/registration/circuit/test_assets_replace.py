"""Tests for upload-or-replace behavior in circuit asset helpers."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

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
