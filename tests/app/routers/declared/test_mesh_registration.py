"""Tests for the mesh registration endpoint."""

import json
from http import HTTPStatus
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError
from fastapi import HTTPException

from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_registration import (
    _create_lod_task_config,
    _register_glb_asset,
)
from app.errors import ApiErrorCode

ENTITY_ID = str(uuid4())
TARGET_MODULE = "app.endpoints.mesh_registration"
ROUTE = f"/declared/{ENTITY_ID}/register-mesh"
FAKE_TEMP_PATH = "fake-temp-mesh.obj"
FAKE_GLB_ASSET_ID = str(uuid4())
FAKE_OBJ_ASSET_ID = str(uuid4())
FAKE_CONFIG_ID = uuid4()

# _prepare_mesh_assets return value for OBJ uploads:
# (glb_asset_id, lod_mesh_asset_id, lod_mesh_format, temp_glb_path)
FAKE_PREPARE_OBJ_RESULT = (FAKE_GLB_ASSET_ID, FAKE_OBJ_ASSET_ID, "obj", "fake-temp.glb")
FAKE_PREPARE_GLB_RESULT = (FAKE_GLB_ASSET_ID, FAKE_GLB_ASSET_ID, "glb", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_client():
    client = MagicMock()
    client.project_context = MagicMock()
    return client


@pytest.fixture
def valid_obj_file():
    content = BytesIO(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3")
    return {"file": ("mesh.obj", content, "application/octet-stream")}


@pytest.fixture
def valid_glb_file():
    content = BytesIO(b"glTF\x02\x00\x00\x00")
    return {"file": ("mesh.glb", content, "application/octet-stream")}


@pytest.fixture
def mock_task_info():
    info = MagicMock()
    info.job_id = uuid4()
    return info


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


def test_register_mesh_obj_success(client, mock_db_client, valid_obj_file, mock_task_info):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            return_value=FAKE_PREPARE_OBJ_RESULT,
        ),
        patch(f"{TARGET_MODULE}._create_lod_task_config", return_value=FAKE_CONFIG_ID),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["entity_id"] == ENTITY_ID
    assert body["status"] == "pending"
    assert body["glb_asset_id"] == FAKE_GLB_ASSET_ID
    assert body["task_job_id"] == str(mock_task_info.job_id)


def test_register_mesh_glb_success(client, mock_db_client, valid_glb_file, mock_task_info):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake-temp.glb"),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            return_value=FAKE_PREPARE_GLB_RESULT,
        ),
        patch(f"{TARGET_MODULE}._create_lod_task_config", return_value=FAKE_CONFIG_ID),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_glb_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["entity_id"] == ENTITY_ID
    assert body["glb_asset_id"] == FAKE_GLB_ASSET_ID
    assert body["status"] == "pending"


def test_register_mesh_unsupported_format(client, mock_db_client):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    content = BytesIO(b"data")
    files = {"file": ("mesh.stl", content, "application/octet-stream")}

    response = client.post(ROUTE, files=files)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"]["code"] == ApiErrorCode.INVALID_REQUEST
    assert ".stl" in response.json()["detail"]["detail"]


def test_register_mesh_invalid_entity_id(client, valid_obj_file):
    response = client.post("/declared/not-a-uuid/register-mesh", files=valid_obj_file)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"]["code"] == ApiErrorCode.INVALID_REQUEST
    assert "UUID" in response.json()["detail"]["detail"]


def test_register_mesh_wrong_entity_type(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    response = client.post(ROUTE, files=valid_obj_file, data={"entity_type": "Circuit"})

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"]["code"] == ApiErrorCode.INVALID_REQUEST
    assert "EMCellMesh" in response.json()["detail"]["detail"]


def test_register_mesh_asset_upload_fails(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            side_effect=HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                    "detail": "upload failed",
                },
            ),
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["detail"]["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_register_mesh_task_config_creation_fails(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            return_value=FAKE_PREPARE_OBJ_RESULT,
        ),
        patch(
            f"{TARGET_MODULE}._create_lod_task_config",
            side_effect=HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                    "detail": "register failed",
                },
            ),
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["detail"]["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_register_mesh_task_submit_fails(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            return_value=FAKE_PREPARE_OBJ_RESULT,
        ),
        patch(f"{TARGET_MODULE}._create_lod_task_config", return_value=FAKE_CONFIG_ID),
        patch(
            f"{TARGET_MODULE}.task_service.submit_task_job",
            side_effect=RuntimeError("ls down"),
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_register_mesh_missing_project_context(client, mock_db_client, valid_obj_file):
    mock_db_client.project_context = None
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            return_value=FAKE_PREPARE_OBJ_RESULT,
        ),
        patch(f"{TARGET_MODULE}._create_lod_task_config", return_value=FAKE_CONFIG_ID),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_register_mesh_cleanup_called_on_success(
    client, mock_db_client, valid_obj_file, mock_task_info
):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    mock_cleanup = MagicMock()

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temps", side_effect=mock_cleanup),
        patch(
            f"{TARGET_MODULE}._prepare_mesh_assets",
            return_value=FAKE_PREPARE_OBJ_RESULT,
        ),
        patch(f"{TARGET_MODULE}._create_lod_task_config", return_value=FAKE_CONFIG_ID),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.ACCEPTED
    mock_cleanup.assert_called_once_with(FAKE_TEMP_PATH, "fake-temp.glb")


def test_register_mesh_cleanup_called_on_exception(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    mock_cleanup = MagicMock()

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(
            f"{TARGET_MODULE}.validate_mesh_reader",
            side_effect=RuntimeError("bad mesh"),
        ),
        patch(f"{TARGET_MODULE}._cleanup_temps", side_effect=mock_cleanup),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    mock_cleanup.assert_called_once_with(FAKE_TEMP_PATH, None)


# ---------------------------------------------------------------------------
# Unit tests: _register_glb_asset
# ---------------------------------------------------------------------------


def test_register_glb_asset_success(tmp_path):
    glb_path = tmp_path / "mesh.glb"
    glb_path.write_bytes(b"glb-data")

    mock_client = MagicMock()
    uploaded_asset = MagicMock()
    uploaded_asset.id = "assets/mesh.glb"
    mock_client.upload_content.return_value = uploaded_asset

    result = _register_glb_asset(mock_client, uuid4(), glb_path)

    assert result == "assets/mesh.glb"
    mock_client.upload_content.assert_called_once()


def test_register_glb_asset_sdk_error(tmp_path):
    glb_path = tmp_path / "mesh.glb"
    glb_path.write_bytes(b"glb-data")

    mock_client = MagicMock()
    mock_client.upload_content.side_effect = EntitySDKError("network failure")

    with pytest.raises(HTTPException) as exc_info:
        _register_glb_asset(mock_client, uuid4(), glb_path)

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


# ---------------------------------------------------------------------------
# Unit tests: _create_lod_task_config
# ---------------------------------------------------------------------------


def test_create_lod_task_config_success():
    mock_client = MagicMock()
    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity

    result = _create_lod_task_config(mock_client, uuid4(), uuid4(), "obj")

    assert result == config_entity.id
    mock_client.register_entity.assert_called_once()
    mock_client.upload_content.assert_called_once()


def test_create_lod_task_config_register_fails():
    mock_client = MagicMock()
    mock_client.register_entity.side_effect = EntitySDKError("register failed")

    with pytest.raises(HTTPException) as exc_info:
        _create_lod_task_config(mock_client, uuid4(), uuid4(), "obj")

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_create_lod_task_config_upload_fails():
    mock_client = MagicMock()
    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity
    mock_client.upload_content.side_effect = EntitySDKError("upload failed")

    with pytest.raises(HTTPException) as exc_info:
        _create_lod_task_config(mock_client, uuid4(), uuid4(), "obj")

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_create_lod_task_config_payload_contains_entity_and_asset():
    mock_client = MagicMock()
    config_entity = MagicMock()
    entity_id = uuid4()
    mesh_asset_id = uuid4()
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity

    _create_lod_task_config(mock_client, entity_id, mesh_asset_id, "glb")

    call_kwargs = mock_client.upload_content.call_args.kwargs
    payload = json.loads(call_kwargs["file_content"])
    assert payload["entity_id"] == str(entity_id)
    assert payload["mesh_asset_id"] == str(mesh_asset_id)
    assert payload["mesh_format"] == "glb"
