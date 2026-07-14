from unittest.mock import MagicMock, patch
from uuid import uuid4

import entitysdk.client
from entitysdk.exception import EntitySDKError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_section_types import router
from app.schemas.morphology_section_types import MorphologySectionTypeOption

ROUTER_MODULE = "app.endpoints.morphology_section_types"


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[user_verified] = lambda: True
    db_client = MagicMock(entitysdk.client.Client)
    app.dependency_overrides[get_client] = lambda: db_client
    return TestClient(app), db_client


@patch(f"{ROUTER_MODULE}.morphology_source_section_type_options")
def test_mapped_morphology_source_properties(mock_options):
    client, db_client = _client()
    source_id = uuid4()
    mock_options.return_value = [
        MorphologySectionTypeOption(value=2, label="Axon"),
        MorphologySectionTypeOption(value=4, label="Apical dendrite"),
    ]

    response = client.get(f"/declared/mapped-morphology-source-properties/{source_id}")

    assert response.status_code == 200
    assert response.json() == {
        "SectionTypes": [
            {"value": 2, "label": "Axon"},
            {"value": 4, "label": "Apical dendrite"},
        ],
        "usability": {},
    }
    mock_options.assert_called_once_with(db_client, source_id)


@patch(f"{ROUTER_MODULE}.morphology_source_section_type_options")
def test_mapped_morphology_source_properties_not_found(mock_options):
    client, _db_client = _client()
    source_id = uuid4()
    mock_options.side_effect = EntitySDKError("not found")

    response = client.get(f"/declared/mapped-morphology-source-properties/{source_id}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


@patch(f"{ROUTER_MODULE}.morphology_source_section_type_options")
def test_mapped_morphology_source_properties_invalid_source(mock_options):
    client, _db_client = _client()
    source_id = uuid4()
    mock_options.side_effect = ValueError("unsupported morphology")

    response = client.get(f"/declared/mapped-morphology-source-properties/{source_id}")

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "INVALID_REQUEST",
        "detail": (
            f"Could not discover morphology section types for {source_id}: unsupported morphology"
        ),
    }
