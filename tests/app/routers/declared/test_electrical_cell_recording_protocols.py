"""Tests for the electrical-cell-recording-protocols endpoint."""

import json
import uuid
from http import HTTPStatus
from unittest.mock import MagicMock

import entitysdk.client
import entitysdk.exception
import pytest
from entitysdk.models import ElectricalCellRecording
from fastapi.testclient import TestClient

from app.dependencies.entitysdk import get_client

from tests.utils import DATA_DIR

ROUTE = "/declared/electrical-cell-recording-protocols"


def _load_recording() -> ElectricalCellRecording:
    return ElectricalCellRecording.model_validate(
        json.loads((DATA_DIR / "electrical_cell_recording.json").read_bytes())
    )


def test_protocols_endpoint_success(client: TestClient, monkeypatch):
    """Endpoint returns per-recording protocols and their union."""
    recording = _load_recording()
    db_client = MagicMock(entitysdk.client.Client)
    db_client.get_entity.return_value = recording
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: db_client)

    rid = str(uuid.uuid4())
    response = client.get(ROUTE, params={"recording_ids": [rid]})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert set(body["by_recording"].keys()) == {rid}
    # The test recording has three stimuli all named "Step"
    assert body["by_recording"][rid] == ["Step"]
    assert body["union"] == ["Step"]


def test_protocols_endpoint_multiple_recordings(client: TestClient, monkeypatch):
    """Endpoint handles multiple recording ids and returns a sorted union."""
    recording = _load_recording()
    db_client = MagicMock(entitysdk.client.Client)
    db_client.get_entity.return_value = recording
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: db_client)

    rid_a = str(uuid.uuid4())
    rid_b = str(uuid.uuid4())
    response = client.get(ROUTE, params={"recording_ids": [rid_a, rid_b]})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert set(body["by_recording"].keys()) == {rid_a, rid_b}
    assert body["union"] == ["Step"]


def test_protocols_endpoint_entitysdk_error(client: TestClient, monkeypatch):
    """EntitySDK errors produce a 500 response."""
    db_client = MagicMock(entitysdk.client.Client)
    db_client.get_entity.side_effect = entitysdk.exception.EntitySDKError("boom")
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: db_client)

    rid = str(uuid.uuid4())
    response = client.get(ROUTE, params={"recording_ids": [rid]})

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_protocols_endpoint_value_error(client: TestClient, monkeypatch):
    """ValueError produces a 404 response."""
    db_client = MagicMock(entitysdk.client.Client)
    db_client.get_entity.side_effect = ValueError("not found")
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: db_client)

    rid = str(uuid.uuid4())
    response = client.get(ROUTE, params={"recording_ids": [rid]})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_protocols_endpoint_empty_stimuli(client: TestClient, monkeypatch):
    """A recording with no stimuli returns an empty protocol list."""
    recording = _load_recording().model_copy(update={"stimuli": []})
    db_client = MagicMock(entitysdk.client.Client)
    db_client.get_entity.return_value = recording
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: db_client)

    rid = str(uuid.uuid4())
    response = client.get(ROUTE, params={"recording_ids": [rid]})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["by_recording"][rid] == []
    assert body["union"] == []
