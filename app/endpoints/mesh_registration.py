"""Tests for the mesh registration endpoint."""

from http import HTTPStatus
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_registration import _register_task_config

ENTITY_ID = str(uuid4())
TARGET_MODULE = "app.endpoints.mesh_registration"
ROUTE = f"/declared/{ENTITY_ID}/register-mesh"
FAKE_TEMP_PATH = "fake-temp-mesh.obj"
FAKE_GLB_ASSET_ID = str(uuid4())
FAKE_OBJ_ASSET_ID = str(uuid4())
FAKE_CONFIG_ID = uuid4()

FAKE_PREPARE_OBJ_RESULT = (FAKE_GLB_ASSET_ID, FAKE_OBJ_ASSET_ID, "obj", "fake-temp.glb")
FAKE_PREPARE_GLB_RESULT = (FAKE_GLB_ASSET_ID, FAKE_GLB_ASSET_ID, "glb", None)


@pytest.fixture
def mock_db_client() -> MagicMock:
    client = MagicMock()
    client.project_context = MagicMock()
    return client


@pytest.fixture
def valid_obj_file() -> dict:
    content = BytesIO(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3")
    return {"file": ("mesh.obj", content, "application/octet-stream")}


@pytest.fixture
def valid_glb_file() -> dict:
    content = BytesIO(b"glTF\x02\x00\x00\x00")
    return {"file": ("mesh.glb", content, "application/octet-stream")}


@pytest.fixture
def mock_task_info() -> MagicMock:
    info = MagicMock()
    info.job_id = uuid4()
    return info


def test_register_mesh_obj_success(
    client: TestClient, mock_db_client: MagicMock, valid_obj_file: dict, mock_task_info: MagicMock
) -> None:
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(f"{TARGET_MODULE}._prepare_mesh_assets", return_value=FAKE_PREPARE_OBJ_RESULT),
        patch(f"{TARGET_MODULE}._register_task_config", return_value=FAKE_CONFIG_ID),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.ACCEPTED  # noqa: S101
    body = response.json()
    assert body["entity_id"] == ENTITY_ID  # noqa: S101
    assert body["status"] == "pending"  # noqa: S101


def test_register_mesh_glb_success(
    client: TestClient, mock_db_client: MagicMock, valid_glb_file: dict, mock_task_info: MagicMock
) -> None:
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake-temp.glb"),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(f"{TARGET_MODULE}._prepare_mesh_assets", return_value=FAKE_PREPARE_GLB_RESULT),
        patch(f"{TARGET_MODULE}._register_task_config", return_value=FAKE_CONFIG_ID),
        patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=mock_task_info),
    ):
        response = client.post(ROUTE, files=valid_glb_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.ACCEPTED  # noqa: S101
    assert response.json()["status"] == "pending"  # noqa: S101


def test_register_mesh_unsupported_format(client: TestClient, mock_db_client: MagicMock) -> None:
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    content = BytesIO(b"data")
    files = {"file": ("mesh.stl", content, "application/octet-stream")}

    response = client.post(ROUTE, files=files)
    client.app.dependency_overrides.pop(get_client, None)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR  # noqa: S101


def test_register_mesh_invalid_entity_id(client: TestClient, valid_obj_file: dict) -> None:
    response = client.post("/declared/not-a-uuid/register-mesh", files=valid_obj_file)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # noqa: S101


def test_register_mesh_wrong_entity_type(
    client: TestClient, mock_db_client: MagicMock, valid_obj_file: dict
) -> None:
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    response = client.post(ROUTE, files=valid_obj_file, data={"entity_type": "Circuit"})
    client.app.dependency_overrides.pop(get_client, None)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR  # noqa: S101


def test_register_mesh_asset_upload_fails(
    client: TestClient, mock_db_client: MagicMock, valid_obj_file: dict
) -> None:
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(f"{TARGET_MODULE}._prepare_mesh_assets", side_effect=HTTPException(status_code=500)),
    ):
        response = client.post(ROUTE, files=valid_obj_file)
    client.app.dependency_overrides.pop(get_client, None)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR  # noqa: S101


def test_register_mesh_task_config_creation_fails(
    client: TestClient, mock_db_client: MagicMock, valid_obj_file: dict
) -> None:
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=FAKE_TEMP_PATH),
        patch(f"{TARGET_MODULE}._cleanup_temps"),
        patch(f"{TARGET_MODULE}._prepare_mesh_assets", return_value=FAKE_PREPARE_OBJ_RESULT),
        patch(f"{TARGET_MODULE}._register_task_config", side_effect=HTTPException(status_code=500)),
    ):
        response = client.post(ROUTE, files=valid_obj_file)
    client.app.dependency_overrides.pop(get_client, None)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR  # noqa: S101


def test_register_task_config_success() -> None:
    mock_client = MagicMock()
    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity
    result = _register_task_config(mock_client, uuid4(), uuid4(), "obj")
    assert result == config_entity.id  # noqa: S101
    mock_client.register_entity.assert_called_once()
    mock_client.upload_file.assert_called_once()


def test_register_task_config_register_fails() -> None:
    mock_client = MagicMock()
    mock_client.register_entity.side_effect = EntitySDKError("register failed")
    with pytest.raises(EntitySDKError):
        _register_task_config(mock_client, uuid4(), uuid4(), "obj")
