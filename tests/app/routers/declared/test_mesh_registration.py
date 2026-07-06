"""Tests for the mesh registration endpoint."""

import asyncio
import pathlib
from http import HTTPStatus
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_registration import (
    _generate_lods_background_task,
    _replace_existing_asset_if_present,
)

ENTITY_ID = str(uuid4())
TARGET_MODULE = "app.endpoints.mesh_registration"
ROUTE = f"/declared/{ENTITY_ID}/register-mesh"
FAKE_GLB_ASSET_ID = uuid4()


async def _run_in_threadpool_passthrough(func, *args, **kwargs):
    return func(*args, **kwargs)


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
def valid_glb_file():
    content = BytesIO(b"glTF-fake-binary-content")
    return {"file": ("mesh.glb", content, "model/gltf-binary")}


@pytest.fixture
def unsupported_file():
    content = BytesIO(b"not a mesh")
    return {"file": ("mesh.stl", content, "application/octet-stream")}


def test_register_mesh_obj_success(client, mock_db_client, valid_obj_file, tmp_path):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    temp_mesh_path = tmp_path / "mesh.obj"
    temp_mesh_path.write_bytes(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3")

    mock_glb_asset = MagicMock()
    mock_glb_asset.id = FAKE_GLB_ASSET_ID
    mock_db_client.upload_file.return_value = mock_glb_asset

    def _fake_convert(_obj_path, glb_path):
        pathlib.Path(glb_path).write_bytes(b"fake-glb")
        return pathlib.Path(glb_path)

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=str(temp_mesh_path)),
        patch(f"{TARGET_MODULE}._convert_obj_to_glb", side_effect=_fake_convert),
        patch(f"{TARGET_MODULE}._replace_existing_asset_if_present"),
        patch(f"{TARGET_MODULE}.run_in_threadpool", side_effect=_run_in_threadpool_passthrough),
        patch(
            f"{TARGET_MODULE}.try_generate_and_upload_lods",
            new_callable=AsyncMock,
            return_value=ENTITY_ID,
        ),
    ):
        response = client.post(ROUTE, files=valid_obj_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "success"
    assert body["lod_generation_status"] == "started"
    assert body["glb_asset_id"] == str(FAKE_GLB_ASSET_ID)
    assert body["entity_id"] == ENTITY_ID

    upload_kwargs = mock_db_client.upload_file.call_args.kwargs
    assert upload_kwargs["entity_id"] == UUID(ENTITY_ID)
    assert upload_kwargs["file_name"] == "mesh.glb"


def test_register_mesh_glb_direct_success(client, mock_db_client, valid_glb_file, tmp_path):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    temp_mesh_path = tmp_path / "mesh.glb"
    temp_mesh_path.write_bytes(b"glTF-fake-binary-content")

    mock_glb_asset = MagicMock()
    mock_glb_asset.id = FAKE_GLB_ASSET_ID
    mock_db_client.upload_file.return_value = mock_glb_asset

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=str(temp_mesh_path)),
        patch(f"{TARGET_MODULE}._replace_existing_asset_if_present"),
        patch(f"{TARGET_MODULE}.run_in_threadpool", side_effect=_run_in_threadpool_passthrough),
        patch(
            f"{TARGET_MODULE}.try_generate_and_upload_lods",
            new_callable=AsyncMock,
            return_value=ENTITY_ID,
        ),
    ):
        response = client.post(ROUTE, files=valid_glb_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "success"
    assert body["lod_generation_status"] == "started"

    upload_kwargs = mock_db_client.upload_file.call_args.kwargs
    assert upload_kwargs["file_name"] == "mesh.glb"


def test_register_mesh_unsupported_extension(client, mock_db_client, unsupported_file):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    response = client.post(ROUTE, files=unsupported_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Unsupported mesh file extension" in response.json()["detail"]


def test_register_mesh_upload_failure_returns_500(client, mock_db_client, valid_glb_file, tmp_path):
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    temp_mesh_path = tmp_path / "mesh.glb"
    temp_mesh_path.write_bytes(b"glTF-fake-binary-content")

    mock_db_client.upload_file.side_effect = RuntimeError("boom")

    with (
        patch(f"{TARGET_MODULE}._save_upload_to_tempfile", return_value=str(temp_mesh_path)),
        patch(f"{TARGET_MODULE}._replace_existing_asset_if_present"),
        patch(f"{TARGET_MODULE}.run_in_threadpool", side_effect=_run_in_threadpool_passthrough),
    ):
        response = client.post(ROUTE, files=valid_glb_file)

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "boom" in response.json()["detail"]
    assert not temp_mesh_path.exists()


def test_replace_existing_asset_if_present_deletes_match():
    existing_asset = MagicMock()
    existing_asset.id = uuid4()
    existing_asset.path = "some/path/mesh.glb"
    entity = MagicMock()
    entity.assets = [existing_asset]

    mock_client = MagicMock()
    mock_client.get_entity.return_value = entity

    entity_id = uuid4()
    _replace_existing_asset_if_present(mock_client, entity_id, "mesh.glb")

    delete_kwargs = mock_client.delete_asset.call_args.kwargs
    assert delete_kwargs["entity_id"] == entity_id
    assert delete_kwargs["asset_id"] == existing_asset.id


def test_replace_existing_asset_if_present_no_match():
    entity = MagicMock()
    entity.assets = []

    mock_client = MagicMock()
    mock_client.get_entity.return_value = entity

    _replace_existing_asset_if_present(mock_client, uuid4(), "mesh.glb")

    mock_client.delete_asset.assert_not_called()


def test_generate_lods_background_task_cleans_up_temp_file(tmp_path):
    lod_source_path = tmp_path / "mesh.obj"
    lod_source_path.write_bytes(b"fake-obj-content")

    mock_client = MagicMock()

    with patch(
        f"{TARGET_MODULE}.try_generate_and_upload_lods",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_generate:
        asyncio.run(_generate_lods_background_task(mock_client, uuid4(), lod_source_path, "obj"))

    mock_generate.assert_awaited_once()
    assert not lod_source_path.exists()


def test_generate_lods_background_task_cleans_up_on_error(tmp_path):
    lod_source_path = tmp_path / "mesh.obj"
    lod_source_path.write_bytes(b"fake-obj-content")

    mock_client = MagicMock()

    with (
        patch(
            f"{TARGET_MODULE}.try_generate_and_upload_lods",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(_generate_lods_background_task(mock_client, uuid4(), lod_source_path, "obj"))

    assert not lod_source_path.exists()
