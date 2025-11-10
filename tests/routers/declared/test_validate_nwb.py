"""Unit tests for the validate_all_nwb_readers function."""

from unittest.mock import ANY, MagicMock, patch

import pytest

from app.endpoints.declared_endpoints import (
    validate_all_nwb_readers,
)

READER_MODULE = "bluepyefe.reader"


class TestValidateAllNWBReaders:
    """Test suite for validate_all_nwb_readers function."""

    @staticmethod
    @patch(f"{READER_MODULE}.TRTNWBReader")
    @patch(f"{READER_MODULE}.ScalaNWBReader")
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_first_reader_succeeds(mock_aibs, mock_bbp, mock_scala, mock_trt):
        """Test that function returns successfully when first reader works."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs_instance = MagicMock()
        mock_aibs_instance.read.return_value = {"data": "some data"}
        mock_aibs.return_value = mock_aibs_instance

        validate_all_nwb_readers("/path/to/file.nwb")

        mock_aibs.assert_called_once_with("/path/to/file.nwb", ANY)
        mock_aibs_instance.read.assert_called_once()

        mock_bbp.assert_not_called()
        mock_scala.assert_not_called()
        mock_trt.assert_not_called()

    @staticmethod
    @patch(f"{READER_MODULE}.TRTNWBReader")
    @patch(f"{READER_MODULE}.ScalaNWBReader")
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_second_reader_succeeds(mock_aibs, mock_bbp, mock_scala, mock_trt):
        """Test that function tries second reader when first fails."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs.side_effect = Exception("AIBS reader failed")

        mock_bbp.__name__ = "BBPNWBReader"
        mock_bbp_instance = MagicMock()
        mock_bbp_instance.read.return_value = {"data": "some data"}
        mock_bbp.return_value = mock_bbp_instance

        validate_all_nwb_readers("/path/to/file.nwb")

        mock_aibs.assert_called_once()
        mock_bbp.assert_called_once_with("/path/to/file.nwb", ANY)
        mock_bbp_instance.read.assert_called_once()

        mock_scala.assert_not_called()
        mock_trt.assert_not_called()

    @staticmethod
    @patch(f"{READER_MODULE}.TRTNWBReader")
    @patch(f"{READER_MODULE}.ScalaNWBReader")
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_last_reader_succeeds(mock_aibs, mock_bbp, mock_scala, mock_trt):
        """Test that function tries all readers until the last one succeeds."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs.side_effect = Exception("AIBS failed")

        mock_bbp.__name__ = "BBPNWBReader"
        mock_bbp.side_effect = Exception("BBP failed")

        mock_scala.__name__ = "ScalaNWBReader"
        mock_scala.side_effect = Exception("Scala failed")

        mock_trt.__name__ = "TRTNWBReader"
        mock_trt_instance = MagicMock()
        mock_trt_instance.read.return_value = {"data": "some data"}
        mock_trt.return_value = mock_trt_instance

        validate_all_nwb_readers("/path/to/file.nwb")

        mock_aibs.assert_called_once()
        mock_bbp.assert_called_once()
        mock_scala.assert_called_once()
        mock_trt.assert_called_once_with("/path/to/file.nwb", ANY)
        mock_trt_instance.read.assert_called_once()

    @staticmethod
    @patch(f"{READER_MODULE}.TRTNWBReader")
    @patch(f"{READER_MODULE}.ScalaNWBReader")
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_all_readers_fail(mock_aibs, mock_bbp, mock_scala, mock_trt):
        """Test that RuntimeError is raised when all readers fail."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs.side_effect = Exception("AIBS failed")

        mock_bbp.__name__ = "BBPNWBReader"
        mock_bbp.side_effect = ValueError("BBP failed")

        mock_scala.__name__ = "ScalaNWBReader"
        mock_scala.side_effect = OSError("Scala failed")

        mock_trt.__name__ = "TRTNWBReader"
        mock_trt.side_effect = RuntimeError("TRT failed")

        with pytest.raises(RuntimeError, match="All NWB readers failed"):
            validate_all_nwb_readers("/path/to/file.nwb")

        mock_aibs.assert_called_once()
        mock_bbp.assert_called_once()
        mock_scala.assert_called_once()
        mock_trt.assert_called_once()

    @staticmethod
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_reader_returns_none(mock_aibs, mock_bbp):
        """Test that function continues when reader.read() returns None."""
        mock_aibs_instance = MagicMock()
        mock_aibs_instance.read.return_value = None
        mock_aibs.return_value = mock_aibs_instance

        mock_bbp_instance = MagicMock()
        mock_bbp_instance.read.return_value = {"data": "some data"}
        mock_bbp.return_value = mock_bbp_instance

        validate_all_nwb_readers("/path/to/file.nwb")

        mock_aibs.assert_called_once()
        mock_aibs_instance.read.assert_called_once()
        mock_bbp.assert_called_once()
        mock_bbp_instance.read.assert_called_once()

    @staticmethod
    @patch(f"{READER_MODULE}.TRTNWBReader")
    @patch(f"{READER_MODULE}.ScalaNWBReader")
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_all_readers_return_none(mock_aibs, mock_bbp, mock_scala, mock_trt):
        """Test that RuntimeError is raised when all readers return None."""
        for mock_reader in (mock_aibs, mock_bbp, mock_scala, mock_trt):
            mock_instance = MagicMock()
            mock_instance.read.return_value = None
            mock_reader.return_value = mock_instance

        with pytest.raises(RuntimeError, match="All NWB readers failed"):
            validate_all_nwb_readers("/path/to/file.nwb")

        mock_aibs.assert_called_once()
        mock_bbp.assert_called_once()
        mock_scala.assert_called_once()
        mock_trt.assert_called_once()

    @staticmethod
    @patch("app.endpoints.declared_endpoints.L")
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_logging_on_reader_failure(mock_aibs, mock_bbp, mock_logger):
        """Test that failures are logged before trying next reader."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs.side_effect = ValueError("AIBS parsing error")

        mock_bbp.__name__ = "BBPNWBReader"
        mock_bbp_instance = MagicMock()
        mock_bbp_instance.read.return_value = {"data": "some data"}
        mock_bbp.return_value = mock_bbp_instance

        validate_all_nwb_readers("/path/to/file.nwb")

        mock_logger.warning.assert_called_once()
        # L.warning("Reader %s failed for file %s: %s", name, path, error)
        call_args = mock_logger.warning.call_args[0]
        assert "Reader" in call_args[0]
        assert "failed" in call_args[0]
        assert call_args[1] == "AIBSNWBReader"
        assert call_args[2] == "/path/to/file.nwb"
        assert "AIBS parsing error" in str(call_args[3])

    @staticmethod
    @patch(f"{READER_MODULE}.BBPNWBReader")
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_reader_instantiation_fails(mock_aibs, mock_bbp):
        """Test that function continues when reader instantiation fails."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs.side_effect = Exception("Cannot instantiate AIBS reader")

        mock_bbp.__name__ = "BBPNWBReader"
        mock_bbp_instance = MagicMock()
        mock_bbp_instance.read.return_value = {"data": "some data"}
        mock_bbp.return_value = mock_bbp_instance

        validate_all_nwb_readers("/path/to/file.nwb")

        mock_bbp.assert_called_once()
        mock_bbp_instance.read.assert_called_once()

    @staticmethod
    @patch(f"{READER_MODULE}.AIBSNWBReader")
    def test_protocols_passed_to_readers(mock_aibs):
        """Test that TEST_PROTOCOLS are passed to each reader."""
        mock_aibs.__name__ = "AIBSNWBReader"
        mock_aibs_instance = MagicMock()
        mock_aibs_instance.read.return_value = {"data": "some data"}
        mock_aibs.return_value = mock_aibs_instance

        file_path = "/path/to/file.nwb"
        validate_all_nwb_readers(file_path)

        assert mock_aibs.call_count == 1
        call_args = mock_aibs.call_args[0]
        assert call_args[0] == file_path
        protocols = call_args[1]
        assert isinstance(protocols, list)
        assert len(protocols) > 0
        assert "APThreshold" in protocols
