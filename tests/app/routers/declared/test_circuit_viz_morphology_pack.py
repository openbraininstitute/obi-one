from http import HTTPStatus
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import _create_temp_dir
from app.endpoints.circuit_visualization import router
from app.services.circuit_morphology_pack import DEFAULT_MAX_SEGMENTS, Refusal, refuse


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def client(tmp_path, mock_client):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[user_verified] = lambda: True
    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[_create_temp_dir] = lambda: tmp_path
    return TestClient(app)


@pytest.fixture
def build():
    with patch("app.endpoints.circuit_visualization.build_circuit_morphology_pack") as mock:
        yield mock


class TestMorphologyPack:
    def test_the_pack_is_sent_as_bytes(self, build, client, mock_client, tmp_path):
        build.return_value = b"MPCK and the rest"
        circuit_id = uuid4()
        response = client.get(f"/circuit/viz/{circuit_id}/morphology-pack")
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.content == b"MPCK and the rest"
        build.assert_called_once_with(
            mock_client, circuit_id, tmp_path, DEFAULT_MAX_SEGMENTS, all_levels=False
        )

    def test_the_viewer_says_how_many_segments_it_draws(self, build, client, mock_client, tmp_path):
        build.return_value = b""
        circuit_id = uuid4()
        response = client.get(f"/circuit/viz/{circuit_id}/morphology-pack?max_segments=500000")
        assert response.status_code == HTTPStatus.OK
        build.assert_called_once_with(mock_client, circuit_id, tmp_path, 500000, all_levels=False)

    def test_every_level_on_request(self, build, client, mock_client, tmp_path):
        build.return_value = b""
        circuit_id = uuid4()
        response = client.get(f"/circuit/viz/{circuit_id}/morphology-pack?all_levels=true")
        assert response.status_code == HTTPStatus.OK
        build.assert_called_once_with(
            mock_client, circuit_id, tmp_path, DEFAULT_MAX_SEGMENTS, all_levels=True
        )

    @pytest.mark.parametrize("max_segments", [0, -5, "many"])
    def test_a_number_of_segments_out_of_range_is_not_taken(self, build, client, max_segments):
        response = client.get(f"/circuit/viz/{uuid4()}/morphology-pack?max_segments={max_segments}")
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        build.assert_not_called()

    def test_a_refusal_carries_its_reason(self, build, client):
        build.side_effect = lambda *_, **__: refuse(Refusal.TOO_MANY_NEURONS, "Too many")
        response = client.get(f"/circuit/viz/{uuid4()}/morphology-pack")
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json()["detail"]["reason"] == "too_many_neurons"
