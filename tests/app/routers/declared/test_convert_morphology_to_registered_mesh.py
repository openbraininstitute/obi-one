import uuid
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import entitysdk.exception
import pytest
from entitysdk.models.cell_morphology import CellMorphology
from entitysdk.types import ContentType

from app.dependencies.entitysdk import get_client

VIRTUAL_LAB_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = "00000000-0000-0000-0000-000000000002"
ROUTE_PREFIX = "/declared"
ENDPOINT = "convert-morphology-to-registered-mesh"

TARGET_MODULE = "app.endpoints.convert_morphology_to_registered_mesh"


@pytest.fixture
def mock_db_client():
    client = MagicMock()
    client.project_context = MagicMock()
    return client


@pytest.fixture
def mock_morphology_entity():
    morph = MagicMock(spec=CellMorphology)
    swc_asset = MagicMock()
    swc_asset.id = str(uuid.uuid4())
    swc_asset.content_type = ContentType.SWC
    morph.assets = [swc_asset]
    return morph


def _make_response(client, cell_id):
    return client.post(
        f"{ROUTE_PREFIX}/{ENDPOINT}/{cell_id}",
        params={"virtual_lab_id": VIRTUAL_LAB_ID, "project_id": PROJECT_ID},
    )


def test_register_morphology_mesh_not_installed(client, mock_db_client):
    cell_id = str(uuid.uuid4())
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=False):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.NOT_IMPLEMENTED
    assert response.json()["detail"] == "Meshing dependencies are not installed on this instance."


def test_register_morphology_mesh_success(client, mock_db_client, mock_morphology_entity):
    cell_id = str(uuid.uuid4())
    new_asset_id = str(uuid.uuid4())

    mock_db_client.get_entity.return_value = mock_morphology_entity
    mock_db_client.download_content.return_value = b"mock swc data"

    uploaded_asset = MagicMock()
    uploaded_asset.id = new_asset_id
    mock_db_client.upload_file.return_value = uploaded_asset

    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}.HAS_MESHING", new=True),
        patch(f"{TARGET_MODULE}._mesh_swc", return_value="fake_path.glb"),
        patch(f"{TARGET_MODULE}.Path") as mock_path,
    ):
        instance = mock_path.return_value
        instance.exists.return_value = True
        instance.stat.return_value.st_size = 1024

        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["asset_id"] == new_asset_id


def test_register_morphology_mesh_no_swc_asset(client, mock_db_client):
    cell_id = str(uuid.uuid4())
    morph = MagicMock(spec=CellMorphology)
    morph.assets = []  # No assets means no SWC

    mock_db_client.get_entity.return_value = morph
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=True):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_register_morphology_mesh_entity_not_found(client, mock_db_client):
    cell_id = str(uuid.uuid4())
    mock_db_client.get_entity.side_effect = entitysdk.exception.EntitySDKError("Not found")
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=True):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_register_morphology_mesh_upload_fails(client, mock_db_client, mock_morphology_entity):
    cell_id = str(uuid.uuid4())
    mock_db_client.get_entity.return_value = mock_morphology_entity
    mock_db_client.download_content.return_value = b"mock swc data"
    mock_db_client.upload_file.side_effect = entitysdk.exception.EntitySDKError("upload error")
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}.HAS_MESHING", new=True),
        patch(f"{TARGET_MODULE}._mesh_swc", return_value="fake_path.glb"),
        patch(f"{TARGET_MODULE}.Path") as mock_path,
    ):
        instance = mock_path.return_value
        instance.exists.return_value = True
        instance.stat.return_value.st_size = 1024

        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["detail"]["code"] == "DATABASE_CLIENT_ERROR"


def test_register_morphology_mesh_replaces_existing_glb(client, mock_db_client):
    cell_id = str(uuid.uuid4())
    new_asset_id = str(uuid.uuid4())

    morph = MagicMock(spec=CellMorphology)
    swc_asset = MagicMock()
    swc_asset.id = str(uuid.uuid4())
    swc_asset.content_type = ContentType.SWC
    
    glb_asset = MagicMock()
    glb_asset.id = str(uuid.uuid4())
    glb_asset.content_type = ContentType.GLB
    
    morph.assets = [swc_asset, glb_asset]

    mock_db_client.get_entity.return_value = morph
    mock_db_client.download_content.return_value = b"mock swc data"
    
    uploaded_asset = MagicMock()
    uploaded_asset.id = new_asset_id
    mock_db_client.upload_file.return_value = uploaded_asset

    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}.HAS_MESHING", new=True),
        patch(f"{TARGET_MODULE}._mesh_swc", return_value="fake_path.glb"),
        patch(f"{TARGET_MODULE}.Path") as mock_path,
    ):
        instance = mock_path.return_value
        instance.exists.return_value = True
        instance.stat.return_value.st_size = 2048

        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.OK
    mock_db_client.delete_asset.assert_called()


def test_register_morphology_mesh_delete_existing_glb_fails(client, mock_db_client):
    cell_id = str(uuid.uuid4())

    morph = MagicMock(spec=CellMorphology)
    swc_asset = MagicMock()
    swc_asset.id = str(uuid.uuid4())
    swc_asset.content_type = ContentType.SWC
    
    glb_asset = MagicMock()
    glb_asset.id = str(uuid.uuid4())
    glb_asset.content_type = ContentType.GLB
    morph.assets = [swc_asset, glb_asset]

    mock_db_client.get_entity.return_value = morph
    mock_db_client.download_content.return_value = b"mock swc data"
    mock_db_client.delete_asset.side_effect = entitysdk.exception.EntitySDKError("delete failed")

    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with (
        patch(f"{TARGET_MODULE}.HAS_MESHING", new=True),
        patch(f"{TARGET_MODULE}._mesh_swc", return_value="fake_path.glb"),
        patch(f"{TARGET_MODULE}.Path") as mock_path,
    ):
        instance = mock_path.return_value
        instance.exists.return_value = True
        instance.stat.return_value.st_size = 1024

        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["detail"]["code"] == "DATABASE_CLIENT_ERROR"
