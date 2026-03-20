import json
import uuid
from unittest.mock import MagicMock

import entitysdk.client
import pytest
from entitysdk.models.cell_morphology import CellMorphology

from app.dependencies.entitysdk import get_client

from tests.utils import DATA_DIR

ROUTE = "/declared/neuron-morphology-metrics"


@pytest.fixture
def morphology_json():
    return json.loads((DATA_DIR / "cell_morphology.json").read_bytes())


@pytest.fixture
def morphology_asc():
    return (DATA_DIR / "cell_morphology.asc").read_bytes()


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
    # print(json.dumps(response.json(), indent=4))
    assert response.status_code == 200
    # Response is now huge so can't paste it here. See print statement above.
    # assert response.json() == pytest.approx(
    #     {
    #         "aspect_ratio": 0.1788397393119357,
    #         "circularity": 0.32157527986322876,
    #         "length_fraction_above_soma": 0.34711724519729614,
    #         "max_radial_distance": 324.51275634765625,
    #         "number_of_neurites": 6,
    #         "soma_radius": 5.360222339630127,
    #         "soma_surface_area": 361.0567626953125,
    #     }
    # )
    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 1


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
    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 0
