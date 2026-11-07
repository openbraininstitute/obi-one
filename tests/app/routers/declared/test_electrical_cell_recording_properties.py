from unittest.mock import MagicMock, patch
from uuid import UUID

import entitysdk.client
import entitysdk.exception
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.electrical_cell_recording_properties import router
from obi_one.scientific.library.recording_summary import ProtocolSummary, RecordingSummary

ROUTER_MODULE = "app.endpoints.electrical_cell_recording_properties"
RECORDING_ID = "00000000-0000-0000-0000-000000000001"


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[user_verified] = lambda: True
    db_client = MagicMock(entitysdk.client.Client)
    app.dependency_overrides[get_client] = lambda: db_client
    return TestClient(app), db_client


def _recording(*stimuli: str) -> MagicMock:
    recording = MagicMock()
    recording.stimuli = [MagicMock() for _ in stimuli]
    for stimulus, name in zip(recording.stimuli, stimuli, strict=True):
        stimulus.name = name
    return recording


def _summaries() -> list[RecordingSummary]:
    return [
        RecordingSummary(
            protocols={
                "IDrest": ProtocolSummary(amp=[0.3, 0.5], ton=[700.0], toff=[2700.0]),
                "IDThreshold": ProtocolSummary(amp=[0.2], ton=[700.0], toff=[2700.0]),
            },
            rheobase={"IDThreshold": 0.2, "IDrest": 0.3},
        ),
        RecordingSummary(
            protocols={"IDrest": ProtocolSummary(amp=[0.45], ton=[20.0])},
            rheobase={"IDrest": None},
        ),
    ]


@patch(f"{ROUTER_MODULE}.get_recording_summary")
@patch(f"{ROUTER_MODULE}.get_electrical_cell_recordings")
def test_mapped_properties_come_from_the_summaries(recordings, summaries):
    """Recordings with a rheobase contribute % amplitudes; others only nA ones."""
    client, _ = _client()
    recordings.return_value = {"a": _recording("IDrest", "IDThreshold"), "b": _recording("IDrest")}
    summaries.side_effect = _summaries()

    response = client.get(
        "/declared/mapped-electrical-cell-recording-properties",
        params={"recording_ids": ["a", "b"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "Protocols": ["IDRestProtocol", "IDThreshProtocol"],
        "ProtocolsByRecording": {
            "a": ["IDRestProtocol", "IDThreshProtocol"],
            "b": ["IDRestProtocol"],
        },
        "AmplitudesByProtocol": {"IDRestProtocol": [0.3, 0.45, 0.5], "IDThreshProtocol": [0.2]},
        "TimingByProtocol": {
            "IDRestProtocol": {"ton": [20.0, 700.0], "toff": [2700.0]},
            "IDThreshProtocol": {"ton": [700.0], "toff": [2700.0]},
        },
        "RheobaseProtocols": ["IDRestProtocol", "IDThreshProtocol"],
        "RelativeAmplitudesByProtocol": {
            "IDRestProtocol": [150.0, 250.0],
            "IDThreshProtocol": [100.0],
        },
        "RheobaseByRecording": {"a": 0.2, "b": None},
    }


@patch(f"{ROUTER_MODULE}.get_recording_summary")
@patch(f"{ROUTER_MODULE}.get_electrical_cell_recordings")
def test_rheobase_protocols_choose_the_reference(recordings, summaries):
    """With IDrest as rheobase protocol, recording a's rheobase is 0.3 nA."""
    client, _ = _client()
    recordings.return_value = {"a": _recording("IDrest", "IDThreshold"), "b": _recording("IDrest")}
    summaries.side_effect = _summaries()

    response = client.get(
        "/declared/mapped-electrical-cell-recording-properties",
        params={"recording_ids": ["a", "b"], "rheobase_protocols": ["IDRestProtocol"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["RheobaseByRecording"] == {"a": 0.3, "b": None}
    assert data["RelativeAmplitudesByProtocol"] == {
        "IDRestProtocol": [100.0, 166.7],
        "IDThreshProtocol": [66.7],
    }


@patch(f"{ROUTER_MODULE}.get_electrical_cell_recordings")
def test_mapped_properties_entitysdk_error(recordings):
    client, _ = _client()
    recordings.side_effect = entitysdk.exception.EntitySDKError("boom")

    response = client.get(
        "/declared/mapped-electrical-cell-recording-properties",
        params={"recording_ids": ["a"]},
    )

    assert response.status_code == 500


@patch(f"{ROUTER_MODULE}.compute_recording_summary_from_nwb")
def test_summary_is_computed_and_returned(compute):
    client, db_client = _client()
    compute.return_value = RecordingSummary(
        protocols={"sAHP": ProtocolSummary(amp=[0.3], long_amp=[0.08], ton=[25.0])},
        rheobase={"IDthresh": 0.2},
    )

    response = client.get(
        "/declared/electrical-cell-recording-summary", params={"recording_id": RECORDING_ID}
    )

    assert response.status_code == 200
    assert response.json() == {
        "version": 1,
        "units": {"current": "nA", "time": "ms"},
        "protocols": {"sAHP": {"amp": [0.3], "long_amp": [0.08], "ton": [25.0]}},
        "rheobase": {"IDthresh": 0.2},
    }
    assert db_client.get_entity.call_args.args == (UUID(RECORDING_ID),)
    db_client.upload_content.assert_not_called()


@patch(f"{ROUTER_MODULE}.compute_recording_summary_from_nwb", return_value=None)
def test_summary_of_a_recording_without_nwb(compute):
    client, _ = _client()

    response = client.get(
        "/declared/electrical-cell-recording-summary", params={"recording_id": RECORDING_ID}
    )

    assert response.status_code == 404
    compute.assert_called_once()


def test_summary_rejects_an_invalid_id():
    client, _ = _client()

    response = client.get(
        "/declared/electrical-cell-recording-summary", params={"recording_id": "not-a-uuid"}
    )

    assert response.status_code == 422


def test_summary_entitysdk_error():
    client, db_client = _client()
    db_client.get_entity.side_effect = entitysdk.exception.EntitySDKError("boom")

    response = client.get(
        "/declared/electrical-cell-recording-summary", params={"recording_id": RECORDING_ID}
    )

    assert response.status_code == 500
