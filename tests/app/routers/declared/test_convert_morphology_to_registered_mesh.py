import uuid
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import entitysdk.exception
import pytest
from entitysdk.models.cell_morphology import CellMorphology
from entitysdk.types import ContentType

from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode

VIRTUAL_LAB_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = "00000000-0000-0000-0000-000000000002"
ROUTE_PREFIX = "/declared"
ENDPOINT = "convert-morphology-to-registered-mesh"

TARGET_MODULE = "app.endpoints.convert_morphology_to_registered_mesh"


@pytest.fixture
def mock_db_client():
    client = MagicMock()
    client.project_context = MagicMock()
    client.select_assets.return_value.first.return_value = None
    return client


@pytest.fixture
def mock_morphology_entity():
    morph = MagicMock(spec=CellMorphology)
    swc_asset = MagicMock()
    swc_asset.id = str(uuid.uuid4())
    swc_asset.content_type = ContentType.application_swc
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
    assert response.json()["message"] == "Meshing dependencies are not installed on this instance."
    assert response.json()["error_code"] == ApiErrorCode.INTERNAL_ERROR


def test_register_morphology_mesh_success(client, mock_db_client, mock_morphology_entity):
    cell_id = str(uuid.uuid4())
    new_asset_id = str(uuid.uuid4())

    mock_db_client.get_entity.return_value = mock_morphology_entity

    mock_db_client.select_assets.return_value.one.return_value = mock_morphology_entity.assets[0]

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
    mock_db_client.get_entity.return_value = morph

    mock_db_client.select_assets.return_value.one.side_effect = (
        entitysdk.exception.IteratorResultError("No asset found")
    )

    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=True):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error_code"] == ApiErrorCode.INVALID_REQUEST
    assert "has no SWC asset" in response.json()["message"]


def test_register_morphology_mesh_entity_not_found(client, mock_db_client):
    cell_id = str(uuid.uuid4())
    mock_db_client.get_entity.side_effect = entitysdk.exception.EntitySDKError("Not found")
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=True):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["error_code"] == ApiErrorCode.NOT_FOUND


def test_register_morphology_mesh_conflict_existing_glb(
    client, mock_db_client, mock_morphology_entity
):
    cell_id = str(uuid.uuid4())
    glb_asset = MagicMock()
    glb_asset.id = "existing_glb_id"

    mock_db_client.get_entity.return_value = mock_morphology_entity

    mock_db_client.select_assets.return_value.first.return_value = glb_asset

    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=True):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["error_code"] == ApiErrorCode.INVALID_REQUEST


def test_register_morphology_mesh_upload_fails(client, mock_db_client, mock_morphology_entity):
    cell_id = str(uuid.uuid4())
    mock_db_client.get_entity.return_value = mock_morphology_entity
    mock_db_client.select_assets.return_value.one.return_value = mock_morphology_entity.assets[0]
    mock_db_client.select_assets.return_value.__iter__.return_value = iter([])
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
    assert response.json()["error_code"] == ApiErrorCode.DATABASE_CLIENT_ERROR


def test_register_morphology_mesh_download_fails(client, mock_db_client, mock_morphology_entity):
    cell_id = str(uuid.uuid4())
    mock_db_client.get_entity.return_value = mock_morphology_entity
    mock_db_client.select_assets.return_value.one.return_value = mock_morphology_entity.assets[0]
    mock_db_client.select_assets.return_value.__iter__.return_value = iter([])

    mock_db_client.download_content.side_effect = entitysdk.exception.EntitySDKError(
        "network error"
    )
    client.app.dependency_overrides[get_client] = lambda: mock_db_client

    with patch(f"{TARGET_MODULE}.HAS_MESHING", new=True):
        response = _make_response(client, cell_id)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["error_code"] == ApiErrorCode.DATABASE_CLIENT_ERROR
