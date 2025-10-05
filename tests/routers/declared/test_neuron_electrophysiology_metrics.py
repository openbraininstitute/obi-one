import json
import uuid
from io import StringIO
from unittest.mock import MagicMock

import entitysdk.client
import pytest
from entitysdk.models import ElectricalCellRecording

from app.dependencies.entitysdk import get_client
from obi_one.scientific.library.ephys_extraction import parse_bpe_logs

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

    assert entitysdk_client_mock.get_entity.call_count == 2
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
    assert (
        "No asset with content type 'application/nwb' found for trace" in response.json()["detail"]
    )
    assert entitysdk_client_mock.get_entity.call_count == 2
    assert entitysdk_client_mock.download_content.call_count == 0


def test_get_defaults_step_like_and_all_features(client, ephys_json, ephys_nwb, monkeypatch):
    """Test defaulting to all step-like protocols and all features when not provided."""
    ephys = ElectricalCellRecording.model_validate(ephys_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = ephys
    entitysdk_client_mock.download_content.return_value = ephys_nwb
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    # No protocols or requested_metrics provided
    response = client.get(f"{ROUTE}/{entity_id}")
    assert response.status_code == 200
    assert any("step" in k for k in response.json()["feature_dict"])


def test_amplitude_filtering(client, ephys_json, ephys_nwb, monkeypatch):
    """Test amplitude filtering."""
    ephys = ElectricalCellRecording.model_validate(ephys_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = ephys
    entitysdk_client_mock.download_content.return_value = ephys_nwb
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()

    response = client.get(f"{ROUTE}/{entity_id}?min_value=0.2&max_value=1.0")
    assert response.status_code == 200
    assert "step_0.6" in response.json()["feature_dict"]

    response = client.get(f"{ROUTE}/{entity_id}?min_value=0.0&max_value=0.0")
    assert response.status_code == 200
    assert response.json() == {"feature_dict": {}}


def test_get_protocol_not_found(client, ephys_json, ephys_nwb, monkeypatch):
    """Test ProtocolNotFoundError is raised when all requested protocols are missing."""
    ephys = ElectricalCellRecording.model_validate(ephys_json)
    entitysdk_client_mock = MagicMock(entitysdk.client.Client)
    entitysdk_client_mock.get_entity.return_value = ephys
    entitysdk_client_mock.download_content.return_value = ephys_nwb
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    entity_id = uuid.uuid4()
    response = client.get(f"{ROUTE}/{entity_id}?protocols=delta")
    assert response.status_code == 404
    assert "None of the requested protocols" in response.text


def test_parse_bpe_logs_extracts_missing_protocols():
    log = StringIO("Protocol 'delta' not found in any cell recordings.\n")
    missing = parse_bpe_logs(log)
    assert missing == ["delta"]
