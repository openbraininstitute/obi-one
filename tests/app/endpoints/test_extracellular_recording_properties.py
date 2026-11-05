"""Tests for the mapped extracellular recording properties endpoint."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from entitysdk.exception import EntitySDKError
from fastapi.testclient import TestClient

from app.application import app
from app.dependencies.entitysdk import get_client
from app.endpoints import extracellular_recording_properties as endpoint
from obi_one.core.exception import OBIONEError

from tests.utils import AUTH_HEADER_USER_1, PROJECT_HEADERS

OPTIONS = [{"value": "Raw/AP0", "label": "AP0"}]


def database() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(_override_check_user_info):
    app.dependency_overrides[get_client] = database
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_client, None)


def get(client, recording_id):
    return client.get(
        f"/declared/mapped-extracellular-recording-properties/{recording_id}",
        headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
    )


class TestMappedExtracellularRecordingProperties:
    def test_it_returns_the_channels_and_a_usability(self, client):
        with patch.object(
            endpoint, "get_extracellular_recording_channel_options", return_value=OPTIONS
        ):
            response = get(client, uuid4())

        assert response.status_code == 200
        assert response.json() == {"Channels": OPTIONS, "usability": {}}

    @pytest.mark.parametrize(
        "error",
        [
            EntitySDKError("no entity"),
            OBIONEError("not redirected"),
            httpx.ConnectError("no storage"),
            OSError("not hdf5"),
            KeyError("no electrodes"),
        ],
    )
    def test_a_recording_that_cannot_be_read_says_which(self, client, error):
        recording_id = uuid4()
        with patch.object(
            endpoint, "get_extracellular_recording_channel_options", side_effect=error
        ):
            response = get(client, recording_id)

        assert response.status_code == 500
        assert str(recording_id) in response.text

    def test_it_needs_a_recording_id(self, client):
        assert get(client, "not-an-id").status_code == 422
