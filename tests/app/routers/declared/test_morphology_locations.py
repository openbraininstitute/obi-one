from unittest.mock import MagicMock, patch
from uuid import uuid4

import entitysdk.client
import pytest
from entitysdk.exception import EntitySDKError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_locations import router
from obi_one.core.exception import ConfigValidationError

ROUTER_MODULE = "app.endpoints.morphology_locations"


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[user_verified] = lambda: True
    db_client = MagicMock(entitysdk.client.Client)
    app.dependency_overrides[get_client] = lambda: db_client
    return TestClient(app), db_client


def _random_locations(**overrides):
    return {
        "type": "RandomMorphologyLocations",
        "random_seed": 0,
        "number_of_locations": 3,
        **overrides,
    }


def _preview_url(entity_id):
    return f"/declared/morphology-locations/preview/{entity_id}"


@patch(f"{ROUTER_MODULE}.preview_morphology_locations")
def test_preview_returns_section_ids_and_offsets(mock_preview):
    client, db_client = _client()
    entity_id = uuid4()
    mock_preview.return_value = [(0, 0.0), (7, 0.25)]

    response = client.post(_preview_url(entity_id), json=_random_locations())

    assert response.status_code == 200
    assert response.json() == {
        "locations": [
            {"section_id": 0, "offset": 0.0},
            {"section_id": 7, "offset": 0.25},
        ]
    }
    assert mock_preview.call_args.args[0] is db_client
    assert mock_preview.call_args.args[1] == entity_id


@patch(f"{ROUTER_MODULE}.preview_morphology_locations")
def test_preview_passes_the_requested_block_through(mock_preview):
    """The block is evaluated as sent, so the preview matches what the workflow would generate."""
    client, _db_client = _client()
    mock_preview.return_value = []

    response = client.post(
        _preview_url(uuid4()),
        json=_random_locations(number_of_locations=9, random_seed=4),
    )

    assert response.status_code == 200
    block = mock_preview.call_args.args[2]
    assert type(block).__name__ == "RandomMorphologyLocations"
    assert block.number_of_locations == 9
    assert block.random_seed == 4


@patch(f"{ROUTER_MODULE}.preview_morphology_locations")
def test_preview_reports_a_missing_entity_as_not_found(mock_preview):
    client, _db_client = _client()
    entity_id = uuid4()
    mock_preview.side_effect = EntitySDKError("not found")

    response = client.post(_preview_url(entity_id), json=_random_locations())

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "error",
    [
        ValueError("Circuit must be a single-neuron circuit."),
        ConfigValidationError("must contain at least one point"),
        KeyError("section_id"),
    ],
)
@patch(f"{ROUTER_MODULE}.preview_morphology_locations")
def test_preview_reports_an_unusable_request_as_a_client_error(mock_preview, error):
    """A config the user can fix must not surface as a 500."""
    client, _db_client = _client()
    entity_id = uuid4()
    mock_preview.side_effect = error

    response = client.post(_preview_url(entity_id), json=_random_locations())

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert str(entity_id) in response.json()["detail"]["detail"]


@patch(f"{ROUTER_MODULE}.preview_morphology_locations")
def test_preview_rejects_a_parameter_sweep(mock_preview):
    """A preview has no scan coordinate, so an unresolved sweep has no single value to draw."""
    client, _db_client = _client()
    mock_preview.side_effect = TypeError("number_of_locations is a list")

    response = client.post(
        _preview_url(uuid4()),
        json=_random_locations(number_of_locations=[3, 5]),
    )

    assert response.status_code == 422
    assert "parameter-sweep lists are not supported" in response.json()["detail"]["detail"]


def test_preview_rejects_an_unknown_block_type():
    client, _db_client = _client()

    response = client.post(
        _preview_url(uuid4()),
        json={"type": "NotAMorphologyLocationBlock"},
    )

    assert response.status_code == 422
