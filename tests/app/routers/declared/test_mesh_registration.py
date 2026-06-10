"""Tests for the mesh registration endpoint."""

import json
from http import HTTPStatus
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.callback import CallBackUrlDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.mesh_registration import (
    _create_lod_task_config,
    _register_obj_asset,
    router as mesh_registration_router,
)
from app.errors import ApiErrorCode

ENTITY_ID = str(uuid4())
TARGET_MODULE = "app.endpoints.mesh_registration"
ROUTE = f"/declared/{ENTITY_ID}/register-mesh"
FAKE_TEMP_PATH = "fake-temp-mesh.obj"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_client():
    client = MagicMock()
    client.project_context = MagicMock()
    return client


@pytest.fixture
def mock_ls_client():
    return MagicMock()


@pytest.fixture
def client(mock_db_client, mock_ls_client):
    app = FastAPI()
    app.include_router(mesh_registration_router)

    app.dependency_overrides[get_client] = lambda: mock_db_client
    app.dependency_overrides[user_verified] = lambda: True
    app.dependency_overrides[LaunchSystemClientDep] = lambda: mock_ls_client
    app.dependency_overrides[CallBackUrlDep] = lambda: "http://callback"

    return TestClient(app)


@pytest.fixture
def valid_obj_file():
    content = BytesIO(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3")
    return {"file": ("mesh.obj", content, "application/octet-stream")}


@pytest.fixture
def mock_task_info():
    info = MagicMock()
    info.job_id = uuid4()
    return info


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


def test_register_mesh_success(client, mock_db_client, valid_obj_file, mock_task_info):
    uploaded_asset = MagicMock()
    uploaded_asset.path = str(uuid4())
    mock_db_client.upload_content.return_value = uploaded_asset

    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_db_client.register_entity.return_value = config_entity

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temp_file"),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["entity_id"] == ENTITY_ID
    assert body["status"] == "pending"
    assert "task_job_id" in body
    assert "obj_asset_id" in body


def test_register_mesh_invalid_entity_id(client, valid_obj_file):
    response = client.post("/declared/not-a-uuid/register-mesh", files=valid_obj_file)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"]["code"] == ApiErrorCode.INVALID_REQUEST
    assert "UUID" in response.json()["detail"]["detail"]


def test_register_mesh_wrong_entity_type(client, valid_obj_file):
    response = client.post(
        ROUTE,
        files=valid_obj_file,
        data={"entity_type": "Circuit"},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"]["code"] == ApiErrorCode.INVALID_REQUEST
    assert "EMCellMesh" in response.json()["detail"]["detail"]


def test_register_mesh_invalid_extension(client):
    bad_file = {"file": ("mesh.txt", BytesIO(b"data"), "text/plain")}
    response = client.post(ROUTE, files=bad_file)
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_register_mesh_obj_upload_fails(client, mock_db_client, valid_obj_file):
    mock_db_client.upload_content.side_effect = EntitySDKError("upload failed")

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temp_file"),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["detail"]["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_register_mesh_task_config_creation_fails(client, mock_db_client, valid_obj_file):
    uploaded_asset = MagicMock()
    uploaded_asset.path = str(uuid4())
    mock_db_client.upload_content.return_value = uploaded_asset
    mock_db_client.register_entity.side_effect = EntitySDKError("register failed")

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temp_file"),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["detail"]["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_register_mesh_task_submit_fails(client, mock_db_client, valid_obj_file):
    uploaded_asset = MagicMock()
    uploaded_asset.path = str(uuid4())
    mock_db_client.upload_content.return_value = uploaded_asset

    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_db_client.register_entity.return_value = config_entity

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temp_file"),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", side_effect=RuntimeError("ls down")),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_register_mesh_missing_project_context(client, mock_db_client, valid_obj_file):
    mock_db_client.project_context = None

    uploaded_asset = MagicMock()
    uploaded_asset.path = str(uuid4())
    mock_db_client.upload_content.return_value = uploaded_asset

    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_db_client.register_entity.return_value = config_entity

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temp_file"),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_register_mesh_cleanup_called_on_success(
    client, mock_db_client, valid_obj_file, mock_task_info
):
    uploaded_asset = MagicMock()
    uploaded_asset.path = str(uuid4())
    mock_db_client.upload_content.return_value = uploaded_asset

    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_db_client.register_entity.return_value = config_entity

    mock_cleanup = MagicMock()

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", return_value=None),
        patch(f"{TARGET_MODULE}._cleanup_temp_file", side_effect=mock_cleanup),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.ACCEPTED
    mock_cleanup.assert_called_once_with(FAKE_TEMP_PATH)


def test_register_mesh_cleanup_called_on_exception(client, valid_obj_file):
    mock_cleanup = MagicMock()

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}.validate_mesh_reader", side_effect=ValueError("bad mesh")),
        patch(f"{TARGET_MODULE}._cleanup_temp_file", side_effect=mock_cleanup),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    mock_cleanup.assert_called_once_with(FAKE_TEMP_PATH)


# ---------------------------------------------------------------------------
# Unit tests: _register_obj_asset
# ---------------------------------------------------------------------------


def test_register_obj_asset_success(tmp_path):
    obj_path = tmp_path / "mesh.obj"
    obj_path.write_bytes(b"v 0 0 0")

    mock_client = MagicMock()
    uploaded_asset = MagicMock()
    uploaded_asset.path = "assets/mesh.obj"
    mock_client.upload_content.return_value = uploaded_asset

    result = _register_obj_asset(mock_client, uuid4(), obj_path)

    assert result == "assets/mesh.obj"
    mock_client.upload_content.assert_called_once()


def test_register_obj_asset_sdk_error(tmp_path):
    obj_path = tmp_path / "mesh.obj"
    obj_path.write_bytes(b"v 0 0 0")

    mock_client = MagicMock()
    mock_client.upload_content.side_effect = EntitySDKError("network failure")

    with pytest.raises(HTTPException) as exc_info:
        _register_obj_asset(mock_client, uuid4(), obj_path)

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

    result = _create_lod_task_config(mock_client, uuid4(), str(uuid4()))

    assert result == config_entity.id
    mock_client.register_entity.assert_called_once()
    mock_client.upload_content.assert_called_once()


def test_create_lod_task_config_register_fails():
    mock_client = MagicMock()
    mock_client.register_entity.side_effect = EntitySDKError("register failed")

    with pytest.raises(HTTPException) as exc_info:
        _create_lod_task_config(mock_client, uuid4(), str(uuid4()))

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_create_lod_task_config_upload_fails():
    mock_client = MagicMock()
    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity
    mock_client.upload_content.side_effect = EntitySDKError("upload failed")

    with pytest.raises(HTTPException) as exc_info:
        _create_lod_task_config(mock_client, uuid4(), str(uuid4()))

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["code"] == ApiErrorCode.ENTITYSDK_API_FAILURE


def test_create_lod_task_config_payload_contains_entity_and_asset():
    mock_client = MagicMock()
    config_entity = MagicMock()
    entity_id = uuid4()
    obj_asset_id = str(uuid4())
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity

    _create_lod_task_config(mock_client, entity_id, obj_asset_id)

    call_kwargs = mock_client.upload_content.call_args.kwargs
    payload = json.loads(call_kwargs["file_content"])
    assert payload["entity_id"] == str(entity_id)
    assert payload["obj_asset_id"] == obj_asset_id
