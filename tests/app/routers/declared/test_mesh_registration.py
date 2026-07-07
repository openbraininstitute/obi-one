"""Tests for the mesh registration endpoint."""

from http import HTTPStatus
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from entitysdk.models import EMCellMesh
from fastapi import HTTPException

from app.dependencies.compute_cell import get_compute_cell
from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_registration import (
    _delete_existing_assets,
    _trigger_mesh_lod_generation_task,
)

ENTITY_ID = str(uuid4())
TARGET_MODULE = "app.endpoints.mesh_registration"
ROUTE = f"/declared/{ENTITY_ID}/register-mesh"
FAKE_GLB_ASSET_ID = uuid4()
FAKE_JOB_ID = uuid4()
FAKE_COMPUTE_CELL = "cell_a"


@pytest.fixture
def mock_db_client():
    client = MagicMock()
    client.project_context = MagicMock()
    client.project_context.project_id = uuid4()
    client.project_context.virtual_lab_id = uuid4()
    return client


@pytest.fixture
def valid_obj_file():
    content = BytesIO(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3")
    return {"file": ("mesh.obj", content, "application/octet-stream")}


def test_register_mesh_success(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    client.app.dependency_overrides[get_compute_cell] = lambda: FAKE_COMPUTE_CELL

    mock_glb_asset = MagicMock()
    mock_glb_asset.id = FAKE_GLB_ASSET_ID

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake.glb"),
        patch(f"{TARGET_MODULE}._ensure_project_context"),
        patch(
            f"{TARGET_MODULE}.run_in_threadpool",
            side_effect=[None, mock_glb_asset, FAKE_JOB_ID],
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)
    client.app.dependency_overrides.pop(get_compute_cell, None)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "pending"
    assert body["glb_asset_id"] == str(FAKE_GLB_ASSET_ID)
    assert body["task_job_id"] == str(FAKE_JOB_ID)
    assert "activity_id" not in body


def test_register_mesh_missing_project_context(client, mock_db_client, valid_obj_file):
    mock_db_client.project_context = None
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    client.app.dependency_overrides[get_compute_cell] = lambda: FAKE_COMPUTE_CELL

    with patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake.glb"):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)
    client.app.dependency_overrides.pop(get_compute_cell, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_register_mesh_upload_failure(client, mock_db_client, valid_obj_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client
    client.app.dependency_overrides[get_compute_cell] = lambda: FAKE_COMPUTE_CELL

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value="fake.glb"),
        patch(f"{TARGET_MODULE}._ensure_project_context"),
        patch(
            f"{TARGET_MODULE}.run_in_threadpool",
            side_effect=RuntimeError("upload failed"),
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)
    client.app.dependency_overrides.pop(get_compute_cell, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "upload failed" in response.json()["detail"]


def test_delete_existing_assets_deletes_matches():
    mock_client = MagicMock()
    entity = MagicMock()
    mock_client.get_entity.return_value = entity

    asset_1 = MagicMock()
    asset_1.id = uuid4()
    asset_2 = MagicMock()
    asset_2.id = uuid4()
    mock_client.select_assets.return_value = [asset_1, asset_2]

    entity_id = uuid4()
    _delete_existing_assets(mock_client, entity_id, "cell_surface_mesh")

    assert mock_client.delete_asset.call_count == 2
    mock_client.delete_asset.assert_any_call(
        entity_id=entity_id, entity_type=EMCellMesh, asset_id=asset_1.id
    )


def test_delete_existing_assets_no_matches():
    mock_client = MagicMock()
    mock_client.get_entity.return_value = MagicMock()
    mock_client.select_assets.return_value = []

    _delete_existing_assets(mock_client, uuid4(), "cell_surface_mesh")

    mock_client.delete_asset.assert_not_called()


def test_trigger_mesh_lod_generation_task_success():
    mock_ls_client = MagicMock()
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"id": str(FAKE_JOB_ID)}
    mock_ls_client.post.return_value = mock_response

    result = _trigger_mesh_lod_generation_task(
        ls_client=mock_ls_client,
        entity_id=uuid4(),
        mesh_asset_id=uuid4(),
        mesh_format="obj",
        project_id=uuid4(),
        virtual_lab_id=uuid4(),
        compute_cell=FAKE_COMPUTE_CELL,
    )

    assert result == FAKE_JOB_ID
    mock_ls_client.post.assert_called_once()
    _, kwargs = mock_ls_client.post.call_args
    assert kwargs["url"] == "/job"
    assert kwargs["json"]["resources"]["compute_cell"] == FAKE_COMPUTE_CELL


def test_trigger_mesh_lod_generation_task_failure():
    mock_ls_client = MagicMock()
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.text = "boom"
    mock_ls_client.post.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        _trigger_mesh_lod_generation_task(
            ls_client=mock_ls_client,
            entity_id=uuid4(),
            mesh_asset_id=uuid4(),
            mesh_format="obj",
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
            compute_cell=FAKE_COMPUTE_CELL,
        )

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "boom" in exc_info.value.detail
