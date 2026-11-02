"""Unit tests for the file-service helpers (upload validation and zip creation)."""

import io
import zipfile
from http import HTTPStatus
from typing import cast

import pytest
from fastapi import HTTPException, UploadFile

from app.services.file import create_zip_file, save_upload_file


def _detail_message(exc: HTTPException) -> str:
    """Extract the inner 'detail' message from the service's dict-shaped error detail."""
    return cast("dict", exc.detail)["detail"]


def _make_upload_file(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), size=len(content))


class TestSaveUploadFile:
    def test_saves_valid_file_with_output_stem(self, tmp_path):
        upload = _make_upload_file("input.SWC", b"morphology-bytes")
        output = save_upload_file(
            upload,
            tmp_path,
            output_stem="cell",
            allowed_extensions={".swc"},
            force_lower_case=True,
        )
        assert output == tmp_path / "cell.swc"
        assert output.read_bytes() == b"morphology-bytes"

    def test_rejects_disallowed_extension(self, tmp_path):
        upload = _make_upload_file("input.txt", b"data")
        with pytest.raises(HTTPException) as exc:
            save_upload_file(
                upload,
                tmp_path,
                output_stem="cell",
                allowed_extensions={".swc", ".h5"},
                force_lower_case=True,
            )
        assert exc.value.status_code == HTTPStatus.BAD_REQUEST
        assert "Invalid file extension" in _detail_message(exc.value)

    def test_rejects_missing_filename(self, tmp_path):
        upload = _make_upload_file("x.swc", b"data")
        upload.filename = None
        with pytest.raises(HTTPException) as exc:
            save_upload_file(
                upload,
                tmp_path,
                output_stem="cell",
                allowed_extensions={".swc"},
                force_lower_case=True,
            )
        assert _detail_message(exc.value) == "No filename provided"

    def test_rejects_empty_file(self, tmp_path):
        upload = _make_upload_file("input.swc", b"")
        with pytest.raises(HTTPException) as exc:
            save_upload_file(
                upload,
                tmp_path,
                output_stem="cell",
                allowed_extensions={".swc"},
                force_lower_case=True,
            )
        assert "File size is 0" in _detail_message(exc.value)

    def test_case_sensitive_extension_rejects_upper_when_not_forced(self, tmp_path):
        upload = _make_upload_file("input.SWC", b"data")
        with pytest.raises(HTTPException):
            save_upload_file(
                upload,
                tmp_path,
                output_stem="cell",
                allowed_extensions={".swc"},
                force_lower_case=False,
            )


class TestCreateZipFile:
    def test_creates_zip_with_all_inputs(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("aaa")
        b.write_text("bbb")
        out = tmp_path / "out.zip"

        create_zip_file([a, b], out, delete_input=False)

        with zipfile.ZipFile(out) as zf:
            assert sorted(zf.namelist()) == ["a.txt", "b.txt"]
            assert zf.read("a.txt") == b"aaa"
        assert a.exists()
        assert b.exists()

    def test_delete_input_removes_source_files(self, tmp_path):
        a = tmp_path / "a.txt"
        a.write_text("aaa")
        out = tmp_path / "out.zip"

        create_zip_file([a], out, delete_input=True)

        assert out.exists()
        assert not a.exists()
