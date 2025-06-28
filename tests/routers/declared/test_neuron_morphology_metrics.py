import json
import uuid
from unittest.mock import MagicMock

import entitysdk.client
import pytest
from entitysdk.models.morphology import ReconstructionMorphology

from app.dependencies.entitysdk import get_client

from tests.utils import DATA_DIR

ROUTE = "/declared/neuron-morphology-metrics"


@pytest.fixture
def morphology_json():
    return json.loads((DATA_DIR / "reconstruction_morphology.json").read_bytes())


@pytest.fixture
def morphology_asc():
    return (DATA_DIR / "reconstruction_morphology.asc").read_bytes()

@pytest.fixture
def morphology_swc():
    return (DATA_DIR / "reconstruction_morphology.swc").read_bytes()


def test_get(client, morphology_json, morphology_swc, monkeypatch):
    morphology = ReconstructionMorphology.model_validate(morphology_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    entitysdk_client_mock.download_content.return_value = morphology_swc
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 200
    assert response.json() == pytest.approx(
        {
            "aspect_ratio": 0.855015167527153,
            "circularity": 0.8014460981216052,
            "length_fraction_above_soma": 0.4389879107475281,
            "max_radial_distance": 965.5757446289062,
            "number_of_neurites": 8,
            "soma_radius": 7.338999928627373,
            "soma_surface_area": 676.8363037109375,
        }
    )
    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 1


def test_get_not_found(client, morphology_json, monkeypatch):
    morphology = ReconstructionMorphology.model_validate(morphology_json)
    morphology = morphology.model_copy(update={"assets": []})
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = morphology
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 404
    assert response.json() == {
        "message": "Asset not found",
        "error_code": "NOT_FOUND",
        "details": None,
    }
    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 0
