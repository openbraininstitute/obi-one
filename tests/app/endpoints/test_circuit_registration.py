"""Unit tests for circuit registration endpoint helpers."""

import tarfile

import pytest
from fastapi import HTTPException

from app.endpoints.circuit_registration import _extract_archive


class TestExtractArchive:
    def test_valid_tar_gz(self, tmp_path):
        # Create a tar.gz with a circuit_config.json inside
        archive_dir = tmp_path / "src"
        archive_dir.mkdir()
        (archive_dir / "circuit_config.json").write_text('{"networks": {}}')
        (archive_dir / "nodes.h5").write_bytes(b"fake-h5")

        archive_path = tmp_path / "circuit.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(archive_dir / "circuit_config.json", arcname="circuit_config.json")
            tar.add(archive_dir / "nodes.h5", arcname="nodes.h5")

        dest = tmp_path / "output"
        dest.mkdir()
        result = _extract_archive(archive_path, dest)

        assert result.exists()
        assert (result / "circuit_config.json").exists()
        assert (result / "nodes.h5").exists()

    def test_not_a_tarfile_raises(self, tmp_path):
        bad_file = tmp_path / "not_tar.gz"
        bad_file.write_text("this is not a tar file")

        dest = tmp_path / "output"
        dest.mkdir()

        with pytest.raises(HTTPException) as exc_info:
            _extract_archive(bad_file, dest)
        assert exc_info.value.status_code == 422
        assert "tar.gz" in exc_info.value.detail

    def test_empty_archive(self, tmp_path):
        archive_path = tmp_path / "empty.tar.gz"
        with tarfile.open(archive_path, "w:gz"):
            pass  # empty archive

        dest = tmp_path / "output"
        dest.mkdir()
        result = _extract_archive(archive_path, dest)
        assert result.exists()
        # Directory exists but is empty
        assert list(result.iterdir()) == []
