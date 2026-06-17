import uuid
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.exception import EntitySDKError

from app.errors import ApiError
from app.services.morphology_registration import (
    register_morphometrics,
    try_generate_and_upload_mesh,
    upload_morphology_content,
    upload_morphology_file,
)


def test_upload_morphology_file_unsupported_extension(tmp_path):
    client = MagicMock()
    file_path = tmp_path / "file.xyz"
    file_path.write_bytes(b"data")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        upload_morphology_file(client, uuid.uuid4(), file_path)


def test_upload_morphology_file_entity_sdk_error(tmp_path):
    client = MagicMock()
    client.upload_file.side_effect = EntitySDKError("Network error")
    file_path = tmp_path / "file.swc"
    file_path.write_bytes(b"data")
    with pytest.raises(EntitySDKError):
        upload_morphology_file(client, uuid.uuid4(), file_path)


def test_upload_morphology_content_entity_sdk_error():
    client = MagicMock()
    client.upload_content.side_effect = EntitySDKError("upload failed")
    with pytest.raises(EntitySDKError):
        upload_morphology_content(client, uuid.uuid4(), "file.swc", b"data")


def test_register_morphometrics_success():
    client = MagicMock()
    client.register_entity.return_value = MagicMock(id="result-id")
    result = register_morphometrics(client, uuid.uuid4(), [])
    assert result.id == "result-id"


def test_register_morphometrics_entity_sdk_error():
    client = MagicMock()
    client.register_entity.side_effect = EntitySDKError("Network error")
    with pytest.raises(EntitySDKError):
        register_morphometrics(client, uuid.uuid4(), [])


def test_try_generate_and_upload_mesh_no_meshing():
    with patch("app.endpoints.convert_morphology_to_registered_mesh.HAS_MESHING", new=False):
        client = MagicMock()
        result = try_generate_and_upload_mesh(client, uuid.uuid4(), swc_bytes=b"swc")
    assert result is None


def test_try_generate_and_upload_mesh_success():
    mesh_id = uuid.uuid4()
    with (
        patch("app.endpoints.convert_morphology_to_registered_mesh.HAS_MESHING", new=True),
        patch(
            "app.endpoints.convert_morphology_to_registered_mesh.mesh_and_register",
            MagicMock(return_value=MagicMock(id=mesh_id)),
        ),
    ):
        client = MagicMock()
        result = try_generate_and_upload_mesh(client, uuid.uuid4(), swc_bytes=b"swc")
    assert result is not None
    assert result.id == mesh_id


def test_try_generate_and_upload_mesh_api_error():
    with (
        patch("app.endpoints.convert_morphology_to_registered_mesh.HAS_MESHING", new=True),
        patch(
            "app.endpoints.convert_morphology_to_registered_mesh.mesh_and_register",
            MagicMock(side_effect=ApiError(message="mesh failed", error_code="TEST_ERR")),
        ),
    ):
        client = MagicMock()
        result = try_generate_and_upload_mesh(client, uuid.uuid4(), swc_bytes=b"swc")
    assert result is None


def test_try_generate_and_upload_mesh_unexpected_error():
    with (
        patch("app.endpoints.convert_morphology_to_registered_mesh.HAS_MESHING", new=True),
        patch(
            "app.endpoints.convert_morphology_to_registered_mesh.mesh_and_register",
            MagicMock(side_effect=RuntimeError("crash")),
        ),
    ):
        client = MagicMock()
        result = try_generate_and_upload_mesh(client, uuid.uuid4(), swc_bytes=b"swc")
    assert result is None


def test_try_generate_and_upload_mesh_from_path(tmp_path):
    mesh_id = uuid.uuid4()
    swc_file = tmp_path / "cell.swc"
    swc_file.write_bytes(b"swc data")
    with (
        patch("app.endpoints.convert_morphology_to_registered_mesh.HAS_MESHING", new=True),
        patch(
            "app.endpoints.convert_morphology_to_registered_mesh.mesh_and_register",
            MagicMock(return_value=MagicMock(id=mesh_id)),
        ) as mock_mesh,
    ):
        client = MagicMock()
        result = try_generate_and_upload_mesh(client, uuid.uuid4(), swc_path=swc_file)
    assert result is not None
    mock_mesh.assert_called_once_with(client, mock_mesh.call_args[0][1], b"swc data")
