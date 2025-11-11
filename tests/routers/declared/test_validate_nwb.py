"""Unit tests for NWB validation endpoint."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.endpoints.nwb_validation import (
    _process_nwb,
    _validate_and_read_nwb_file,
    test_nwb_file,
)


class TestValidateNWBFile:
    """Test suite for NWB validation endpoint functions."""

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_valid_nwb_file():
        """Test that valid .nwb file passes validation."""
        content = b"mock nwb content"
        file = UploadFile(
            filename="test.nwb",
            file=BytesIO(content)
        )
        
        result = await _validate_and_read_nwb_file(file)
        
        assert result[0] == content
        assert result[1] == ".nwb"

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_invalid_extension():
        """Test that invalid file extension raises HTTPException."""
        from fastapi import HTTPException  # noqa: PLC0415
        
        file = UploadFile(
            filename="test.txt",
            file=BytesIO(b"content")
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await _validate_and_read_nwb_file(file)
        
        assert exc_info.value.status_code == 400
        assert "Invalid file extension" in str(exc_info.value.detail)

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_empty_file():
        """Test that empty file raises HTTPException."""
        from fastapi import HTTPException  # noqa: PLC0415
        
        file = UploadFile(
            filename="test.nwb",
            file=BytesIO(b"")
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await _validate_and_read_nwb_file(file)
        
        assert exc_info.value.status_code == 400
        assert "empty" in str(exc_info.value.detail).lower()

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_no_filename():
        """Test that file without filename raises HTTPException."""
        from fastapi import HTTPException  # noqa: PLC0415
        
        file = UploadFile(
            filename="",
            file=BytesIO(b"content")
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await _validate_and_read_nwb_file(file)
        
        assert exc_info.value.status_code == 400

    @staticmethod
    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_process_nwb_success(mock_subprocess):
        """Test successful NWB processing with pynwb-validate."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"valid", b"")
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process
        
        file = UploadFile(filename="test.nwb", file=BytesIO(b"content"))
        
        result = await _process_nwb(file, "test.nwb")
        
        assert result is None
        mock_subprocess.assert_called_once()
        assert "pynwb-validate" in str(mock_subprocess.call_args)

    @staticmethod
    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_process_nwb_validation_fails(mock_subprocess):
        """Test that validation failure raises HTTPException."""
        from fastapi import HTTPException  # noqa: PLC0415
        
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"Validation error")
        mock_process.returncode = 1
        mock_subprocess.return_value = mock_process
        
        file = UploadFile(filename="test.nwb", file=BytesIO(b"content"))
        
        with pytest.raises(HTTPException) as exc_info:
            await _process_nwb(file, "test.nwb")
        
        assert exc_info.value.status_code == 400
        assert "validation failed" in str(exc_info.value.detail).lower()

    @staticmethod
    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_process_nwb_tool_not_found(mock_subprocess):
        """Test that missing pynwb-validate tool raises HTTPException."""
        from fastapi import HTTPException  # noqa: PLC0415
        
        mock_subprocess.side_effect = FileNotFoundError("pynwb-validate not found")
        
        file = UploadFile(filename="test.nwb", file=BytesIO(b"content"))
        
        with pytest.raises(HTTPException) as exc_info:
            await _process_nwb(file, "test.nwb")
        
        assert exc_info.value.status_code == 500
        assert "validation tool" in str(exc_info.value.detail).lower()

    @staticmethod
    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_process_nwb_unexpected_error(mock_subprocess):
        """Test that unexpected errors are handled properly."""
        from fastapi import HTTPException  # noqa: PLC0415
        
        mock_subprocess.side_effect = RuntimeError("Unexpected error")
        
        file = UploadFile(filename="test.nwb", file=BytesIO(b"content"))
        
        with pytest.raises(HTTPException) as exc_info:
            await _process_nwb(file, "test.nwb")
        
        assert exc_info.value.status_code == 500
        assert "unexpected error" in str(exc_info.value.detail).lower()

    @staticmethod
    @pytest.mark.asyncio
    @patch("pathlib.Path.unlink")
    @patch("tempfile.NamedTemporaryFile")
    @patch("app.endpoints.nwb_validation._process_nwb")
    @patch("app.endpoints.nwb_validation._validate_and_read_nwb_file")
    async def test_test_nwb_file_endpoint(
        mock_validate, mock_process, mock_tempfile
    ):
        """Test the complete test_nwb_file endpoint."""
        # Mock validation
        mock_validate.return_value = (b"content", ".nwb")
        
        # Mock tempfile
        mock_temp = MagicMock()
        mock_temp.__enter__ = MagicMock(return_value=mock_temp)
        mock_temp.__exit__ = MagicMock(return_value=None)
        mock_temp.name = "test123.nwb"
        mock_tempfile.return_value = mock_temp
        
        # Mock process (successful validation)
        mock_process.return_value = None
        
        file = UploadFile(filename="test.nwb", file=BytesIO(b"content"))
        
        # Note: This assumes test_nwb_file is accessible. If it's not exported,
        # you may need to test via the router or make it accessible
        result = await test_nwb_file(file)
        
        assert result is None
        mock_validate.assert_called_once()
        mock_process.assert_called_once()
        mock_temp.write.assert_called_once_with(b"content")
        