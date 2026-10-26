"""Tests for the mapped electrical cell recording properties endpoint."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.application import app
from app.dependencies.entitysdk import get_client

from tests.utils import AUTH_HEADER_USER_1, PROJECT_HEADERS

ENDPOINT = "/declared/mapped-electrical-cell-recording-properties"


def _fake_recording(recording_id):
    return SimpleNamespace(id=recording_id, stimuli=[])


@pytest.fixture
def mock_client():
    mock = MagicMock()
    mock.get_entity.side_effect = lambda entity_id, **_: _fake_recording(entity_id)
    app.dependency_overrides[get_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_client, None)


@pytest.fixture
def client(_override_check_user_info, mock_client):
    """Test client with mocked db_client dependency."""
    with TestClient(app) as test_client:
        test_client.mock_client = mock_client
        yield test_client


class TestMappedElectricalCellRecordingPropertiesEndpoint:
    """Tests for GET /declared/mapped-electrical-cell-recording-properties."""

    def test_fetches_each_recording_once(self, client):
        first_id, second_id = uuid4(), uuid4()
        response = client.get(
            ENDPOINT,
            params={"recording_ids": [str(first_id), str(second_id)]},
            headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
        )

        assert response.status_code == 200
        assert client.mock_client.get_entity.call_count == 2
        assert response.json() == {
            "Protocols": [],
            "ProtocolsByRecording": {str(first_id): [], str(second_id): []},
            "AmplitudesByProtocol": {},
        }
