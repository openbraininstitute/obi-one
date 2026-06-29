"""Tests for the mesh registration endpoint."""

from http import HTTPStatus
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError

from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_registration import (
    _register_task_config,
)

ENTITY_ID = str(uuid4())
TARGET_MODULE = "app.endpoints.mesh_registration"
ROUTE = f"/declared/{ENTITY_ID}/register-mesh"
FAKE_CONFIG_ID = uuid4()
FAKE_GLB_ASSET_ID = uuid4()


@pytest.fixture
def mock_db_client():
    client = MagicMock()
    client.project_context = MagicMock()
    client.project_context.project_id = "test-project"
    return client


@pytest.fixture
def valid_obj_file():
    content = BytesIO(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3")
    return {"file": ("mesh.obj", content, "application/octet-stream")}


@pytest.fixture
def mock_task_info():
    info = MagicMock()
    info.job_id = uuid4()
    info.activity_id = uuid4()
    return info


def test_register_mesh_success(client, mock_db_client, valid_obj_file, mock_task_info):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    mock_glb_asset = MagicMock()
    mock_glb_asset.id = FAKE_GLB_ASSET_ID

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake.glb"),
        patch(f"{TARGET_MODULE}._ensure_project_context"),
        patch(
            f"{TARGET_MODULE}.run_in_threadpool",
            side_effect=[mock_glb_asset, FAKE_CONFIG_ID, mock_task_info],
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["entity_id"] == ENTITY_ID
    assert body["status"] == "pending"
    assert body["glb_asset_id"] == str(FAKE_GLB_ASSET_ID)


def test_register_mesh_missing_project_context(client, mock_db_client, valid_obj_file):
    mock_db_client.project_context = None
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_register_mesh_upload_fails(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake.glb"),
        patch(f"{TARGET_MODULE}.run_in_threadpool", side_effect=Exception("upload failed")),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_register_task_config_success():
    mock_client = MagicMock()
    config_entity = MagicMock()
    config_entity.id = uuid4()
    mock_client.register_entity.return_value = config_entity

    with patch("tempfile.NamedTemporaryFile"):
        result = _register_task_config(mock_client, uuid4(), uuid4(), "obj")

    assert result == config_entity.id
    mock_client.register_entity.assert_called_once()
    mock_client.upload_file.assert_called_once()


def test_register_task_config_register_fails():
    mock_client = MagicMock()
    mock_client.register_entity.side_effect = EntitySDKError("register failed")

    with pytest.raises(EntitySDKError):
        _register_task_config(mock_client, uuid4(), uuid4(), "obj")
