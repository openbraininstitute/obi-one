from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

MODULE_PATH = "app.declared_endpoints"
# Use the full route path for consistency with the provided test file style
ROUTE = "/declared/validate-nwb-file"


# --- Pydantic Schema (Must match the endpoint's return type) ---
class NWBValidationResponse(BaseModel):
    """Schema for the NWB file validation success response."""

    status: str
    message: str


# --- Fixtures ---


@pytest.fixture
def mock_nwb_content():
    """Provides placeholder content for a valid NWB file."""
    # Unit tests only need enough bytes to be read by the endpoint,
    # as the core logic is mocked.
    return b"NWB file placeholder content"


# --- Test Class ---


class TestNWBFileValidation:
    @patch(f"{MODULE_PATH}.validate_all_nwb_readers")
    @staticmethod
    def test_validate_nwb_file_success(mock_validator: MagicMock, client, mock_nwb_content):
        """Tests successful validation using a valid .nwb file."""

        mock_validator.return_value = None  # Mock validation success

        response = client.post(
            ROUTE, files={"file": ("test.nwb", mock_nwb_content, "application/octet-stream")}
        )

        # ASSERT
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {
            "status": "success",
            "message": "NWB file validation successful.",
        }
        assert mock_validator.called

    @patch(f"{MODULE_PATH}.validate_all_nwb_readers")
    @staticmethod
    def test_validate_nwb_file_validation_failure(
        mock_validator: MagicMock, client, mock_nwb_content
    ):
        """Tests handling of a validation failure (RuntimeError) from the NWB readers."""

        # ARRANGE
        mock_validator.side_effect = RuntimeError("All NWB readers failed.")

        # ACT
        response = client.post(
            ROUTE,
            files={
                "file": (
                    "invalid_but_correct_ext.nwb",
                    mock_nwb_content,
                    "application/octet-stream",
                )
            },
        )

        # ASSERT
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # 422
        assert response.json()["detail"] == "NWB validation failed: All NWB readers failed."
        assert mock_validator.called

    @pytest.mark.parametrize("invalid_ext", [".txt", ".swc", ".h5", ".asc", ".NWB"])
    @patch(f"{MODULE_PATH}.validate_all_nwb_readers")
    @staticmethod
    def test_validate_nwb_file_invalid_extension(mock_validator: MagicMock, client, invalid_ext):
        """Tests file upload with unsupported extensions (including previously allowed ones)."""

        # ARRANGE
        content = b"Some data"

        # ACT
        response = client.post(
            ROUTE,
            # Note: Filenames are case-sensitive on the extension check unless lowercase() is used.
            # Assuming the check is case-insensitive if .NWB is tested.
            files={"file": (f"data{invalid_ext}", content, "application/octet-stream")},
        )

        # ASSERT
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["detail"] == "Invalid file extension. Must be .nwb"
        assert not mock_validator.called

    @patch(f"{MODULE_PATH}.validate_all_nwb_readers")
    @staticmethod
    def test_validate_nwb_file_empty_file(mock_validator: MagicMock, client):
        """Tests file upload with an empty file (handled by _handle_empty_file)."""

        # ARRANGE
        empty_content = b""

        # ACT
        response = client.post(
            ROUTE, files={"file": ("empty.nwb", empty_content, "application/octet-stream")}
        )

        # ASSERT
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["detail"] == "Uploaded file is empty"
        assert not mock_validator.called

    @patch(f"{MODULE_PATH}.Path.write_bytes")
    @patch(f"{MODULE_PATH}.validate_all_nwb_readers")
    @staticmethod
    def test_validate_nwb_file_disk_write_error(
        mock_validator: MagicMock, mock_write_bytes: MagicMock, client, mock_nwb_content
    ):
        """Tests handling of an error when writing the file to disk (Internal Server Error)."""

        mock_write_bytes.side_effect = OSError("Simulated disk write failure")

        response = client.post(
            ROUTE, files={"file": ("disk_fail.nwb", mock_nwb_content, "application/octet-stream")}
        )

        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "Failed to write file to disk"
        assert not mock_validator.called
