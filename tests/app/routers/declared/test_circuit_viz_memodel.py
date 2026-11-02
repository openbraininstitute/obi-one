from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.types import AssetLabel, ContentType
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.circuit_visualization import memodel_router as router
from app.schemas.circuit_visualization import MorphoViewerTreeItemType
from app.services.circuit_visualization import load_memodel_morphology

# Lists the dendrite before the axon, so file order and nrn_order disagree.
_DENDRITE_BEFORE_AXON_SWC = b"""\
1 1 0 0 0 5 -1
2 3 0 5 0 1 1
3 3 0 10 0 1 2
4 2 0 -5 0 1 1
5 2 0 -10 0 1 4
"""


def _memodel_client(content: bytes = _DENDRITE_BEFORE_AXON_SWC) -> MagicMock:
    morphology = SimpleNamespace(
        id=uuid4(),
        name="test-morphology",
        assets=[
            SimpleNamespace(
                id=uuid4(),
                content_type=ContentType.application_swc,
                label=AssetLabel.morphology,
            )
        ],
    )
    client = MagicMock()
    client.get_entity.return_value = SimpleNamespace(id=uuid4(), morphology=morphology)
    client.download_content.return_value = content
    return client


@pytest.fixture
def test_client():
    def _build(client: MagicMock) -> TestClient:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_client] = lambda: client
        app.dependency_overrides[user_verified] = lambda: None
        return TestClient(app)

    return _build


def test_memodel_morphology_is_served_in_nrn_order(test_client):
    """The viewer's section ids must match the ones the location blocks resolve.

    `ExplicitMorphologyLocations` reads `morphology.section(section_id - 1)` off an
    nrn_order morphology, so serving this endpoint in file order would hand the viewer
    ids that name a different branch.
    """
    response = test_client(_memodel_client()).get(f"/memodel/viz/{uuid4()}/morphology")

    assert response.status_code == HTTPStatus.OK
    neurites = [section for section in response.json() if section["id"] != "soma"]
    assert [section["type"] for section in neurites] == [
        MorphoViewerTreeItemType.Axon,
        MorphoViewerTreeItemType.BasalDendrite,
    ]


def test_memodel_morphology_reports_soma_as_section_zero(test_client):
    response = test_client(_memodel_client()).get(f"/memodel/viz/{uuid4()}/morphology")

    sections = response.json()
    soma = next(section for section in sections if section["id"] == "soma")
    assert soma["sonata_section_id"] == 0
    assert [section["sonata_section_id"] for section in sections if section["id"] != "soma"] == [
        1,
        2,
    ]


def test_a_missing_memodel_is_not_found(test_client):
    client = MagicMock()
    client.get_entity.side_effect = EntitySDKError("no such entity")

    response = test_client(client).get(f"/memodel/viz/{uuid4()}/morphology")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_a_memodel_without_a_usable_asset_is_rejected(test_client):
    client = _memodel_client()
    client.get_entity.return_value.morphology.assets = [
        SimpleNamespace(
            id=uuid4(),
            content_type=ContentType.application_json,
            label=AssetLabel.morphology,
        )
    ]

    response = test_client(client).get(f"/memodel/viz/{uuid4()}/morphology")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_embedded_morphology_assets_are_not_refetched():
    """Save a round trip when the MEModel already carries its morphology's assets."""
    client = _memodel_client()

    load_memodel_morphology(client, client.get_entity.return_value)

    client.get_entity.assert_not_called()
