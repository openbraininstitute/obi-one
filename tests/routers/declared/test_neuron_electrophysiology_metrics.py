import json
import uuid
from unittest.mock import MagicMock

import entitysdk.client
import pytest
from entitysdk.models import ElectricalCellRecording

from app.dependencies.entitysdk import get_client

from tests.utils import DATA_DIR

ROUTE = "/declared/electrophysiologyrecording-metrics"


@pytest.fixture
def ephys_json():
    return json.loads((DATA_DIR / "electrical_cell_recording.json").read_bytes())


@pytest.fixture
def ephys_nwb():
    return (DATA_DIR / "S1FL_L5_DBC_cIR_4.nwb").read_bytes()


def test_get(client, ephys_json, ephys_nwb, monkeypatch):
    ephys = ElectricalCellRecording.model_validate(ephys_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = ephys
    entitysdk_client_mock.download_content.return_value = ephys_nwb
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 200

    features = response.json()["feature_dict"]["step_0"]

    assert features["spike_count"]["avg"] == pytest.approx(1.6667, abs=1e-3)
    assert features["spike_count"]["num_traces"] == 3
    assert features["time_to_first_spike"]["avg"] == pytest.approx(6.625, abs=1e-4)

    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 1


def test_get_not_found(client, ephys_json, monkeypatch):
    ephys = ElectricalCellRecording.model_validate(ephys_json)
    ephys = ephys.model_copy(update={"assets": []})
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = ephys
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 500
    assert "No asset with content type 'application/nwb' found for trace" in response.json()["detail"]
    assert entitysdk_client_mock.get_entity.call_count == 1
    assert entitysdk_client_mock.download_content.call_count == 0
