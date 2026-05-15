import json
import uuid
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import entitysdk.client
import entitysdk.exception
import pytest
from entitysdk.models.cell_morphology import CellMorphology

from app.dependencies.entitysdk import get_client

from tests.utils import DATA_DIR

ROUTE = "/declared/neuron-morphology-metrics"


@pytest.fixture
def morphology_json():
    return json.loads((DATA_DIR / "cell_morphology.json").read_bytes())


@pytest.fixture
def morphology_swc():
    return (DATA_DIR / "cell_morphology.swc").read_bytes()


def test_get(client, morphology_json, morphology_swc, monkeypatch):
    morphology = CellMorphology.model_validate(morphology_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    entitysdk_client_mock.download_content.return_value = morphology_swc
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 200
    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 1


def test_get_with_requested_metrics(client, morphology_json, morphology_swc, monkeypatch):
    morphology = CellMorphology.model_validate(morphology_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    entitysdk_client_mock.download_content.return_value = morphology_swc
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(
        f"{ROUTE}/{entity_id}", params={"requested_metrics": ["aspect_ratio", "circularity"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert "aspect_ratio" in data
    assert "circularity" in data


def test_get_not_found(client, morphology_json, monkeypatch):
    morphology = CellMorphology.model_validate(morphology_json)
    morphology = morphology.model_copy(update={"assets": []})
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 500
    assert response.json() == {
        "message": "Internal error retrieving the asset.",
        "error_code": "INTERNAL_ERROR",
        "details": None,
    }


def test_get_sdk_error(client, monkeypatch):
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    with patch("app.endpoints.morphology_metrics.get_morphology_metrics") as mock_get:
        mock_get.side_effect = entitysdk.exception.EntitySDKError("SDK Error")
        response = client.get(f"{ROUTE}/{entity_id}")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"


def test_register_morphology_metrics_success(client, morphology_json, monkeypatch):
    entity_id = uuid.uuid4()
    measurement_id = uuid.uuid4()

    h5_asset = MagicMock()
    h5_asset.content_type = "application/x-hdf5"
    h5_asset.label = "morphology"
    h5_asset.id = uuid.uuid4()

    morphology = CellMorphology.model_validate(morphology_json)
    morphology = morphology.model_copy(update={"assets": [h5_asset]})

    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    entitysdk_client_mock.download_content.return_value = b"dummy h5 content"

    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    with (
        patch("app.endpoints.morphology_metrics.run_morphology_analysis") as mock_run,
        patch("app.endpoints.morphology_metrics.register_measurements") as mock_reg,
    ):
        mock_run.return_value = ["metric1", "metric2"]
        mock_registered_entity = MagicMock()
        mock_registered_entity.id = measurement_id
        mock_reg.return_value = mock_registered_entity

        response = client.post(f"{ROUTE}/{entity_id}/register")

    assert response.status_code == 200
    assert response.json() == {"measurement_entity_id": str(measurement_id), "status": "success"}


def test_register_morphology_metrics_no_h5_asset(client, morphology_json, monkeypatch):
    entity_id = uuid.uuid4()
    morphology = CellMorphology.model_validate(morphology_json)
    morphology = morphology.model_copy(update={"assets": []})

    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    response = client.post(f"{ROUTE}/{entity_id}/register")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {"detail": "No H5 asset on morphology"}


def test_register_morphology_metrics_asset_no_id(client, morphology_json, monkeypatch):
    entity_id = uuid.uuid4()

    h5_asset = MagicMock()
    h5_asset.content_type = "application/x-hdf5"
    h5_asset.label = "morphology"
    h5_asset.id = None

    morphology = CellMorphology.model_validate(morphology_json)
    morphology = morphology.model_copy(update={"assets": [h5_asset]})

    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    response = client.post(f"{ROUTE}/{entity_id}/register")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {"detail": "Asset has no id"}
