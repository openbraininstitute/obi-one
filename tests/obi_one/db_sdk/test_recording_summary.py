"""Tests for the recording-summary helpers in ``db_sdk``."""

from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from entitysdk.types import AssetLabel

from obi_one.db_sdk.db_sdk import (
    amplitudes_by_protocol_class,
    compute_recording_summary_from_nwb,
    fetch_recording_summary,
    get_recording_protocols,
    get_recording_summary,
)
from obi_one.scientific.library.recording_summary import ProtocolSummary, RecordingSummary

_RID_1 = "00000000-0000-0000-0000-000000000001"
_RID_2 = "00000000-0000-0000-0000-000000000002"
_DB_SDK = "obi_one.db_sdk.db_sdk"


def _summary() -> RecordingSummary:
    return RecordingSummary(
        protocols={
            "IDrest": ProtocolSummary(amp=[0.1, 0.2, 0.3]),
            "IDthresh": ProtocolSummary(amp=[0.15]),
        },
        rheobase={"IDrest": 0.2, "IDthresh": 0.15},
    )


def _asset(label: AssetLabel, asset_id: str = "asset-1") -> Mock:
    asset = Mock()
    asset.label = label
    asset.id = asset_id
    return asset


def _recording(*labels: AssetLabel, stimuli: list[str] | None = None) -> Mock:
    recording = Mock()
    recording.id = UUID(_RID_1)
    recording.assets = [_asset(label, f"asset-{i}") for i, label in enumerate(labels)]
    recording.stimuli = [Mock(name=name) for name in stimuli or []]
    for stimulus, name in zip(recording.stimuli, stimuli or [], strict=True):
        stimulus.name = name
    return recording


class TestFetchRecordingSummary:
    def test_reads_the_recording_summary_asset(self):
        recording = _recording(AssetLabel.nwb, AssetLabel.recording_summary)
        client = Mock()
        client.fetch_content.return_value = _summary().model_dump_json().encode()

        assert fetch_recording_summary(client, recording) == _summary()
        assert client.fetch_content.call_args.kwargs["asset_or_id"].id == "asset-1"

    def test_no_summary_asset(self):
        client = Mock()
        assert fetch_recording_summary(client, _recording(AssetLabel.nwb)) is None
        client.fetch_content.assert_not_called()

    def test_invalid_content_returns_none(self):
        client = Mock()
        client.fetch_content.return_value = b'{"version": 1, "amplitudes_na": []}'
        assert fetch_recording_summary(client, _recording(AssetLabel.recording_summary)) is None

    def test_last_of_several_summaries_is_used(self):
        recording = _recording(AssetLabel.recording_summary, AssetLabel.recording_summary)
        client = Mock()
        client.fetch_content.return_value = _summary().model_dump_json().encode()

        fetch_recording_summary(client, recording)

        assert client.fetch_content.call_args.kwargs["asset_or_id"].id == "asset-1"


class TestComputeRecordingSummaryFromNwb:
    def test_downloads_the_nwb_and_computes(self):
        client = Mock()
        client.fetch_assets.return_value.one.return_value.path = "downloaded/cell.nwb"
        with patch(f"{_DB_SDK}.compute_recording_summary", return_value=_summary()) as compute:
            summary = compute_recording_summary_from_nwb(client, _recording(AssetLabel.nwb))

        assert summary == _summary()
        compute.assert_called_once_with(Path("downloaded/cell.nwb"))

    def test_no_nwb_asset(self):
        client = Mock()
        assert compute_recording_summary_from_nwb(client, _recording()) is None
        client.fetch_assets.assert_not_called()


class TestGetRecordingSummary:
    def test_stored_summary_avoids_the_nwb(self):
        client = Mock()
        client.fetch_content.return_value = _summary().model_dump_json().encode()
        recording = _recording(AssetLabel.nwb, AssetLabel.recording_summary)

        assert get_recording_summary(client, recording) == _summary()
        client.fetch_assets.assert_not_called()

    def test_falls_back_to_the_nwb(self):
        client = Mock()
        with patch(
            f"{_DB_SDK}.compute_recording_summary_from_nwb", return_value=_summary()
        ) as compute:
            summary = get_recording_summary(client, _recording(AssetLabel.nwb))

        assert summary == _summary()
        compute.assert_called_once()


def test_amplitudes_by_protocol_class_unions_recordings():
    other = RecordingSummary(
        protocols={"IDrest": ProtocolSummary(amp=[0.3, 0.4]), "Unknown": ProtocolSummary(amp=[1])}
    )
    assert amplitudes_by_protocol_class({"a": _summary(), "b": other, "c": None}) == {
        "IDRestProtocol": [0.1, 0.2, 0.3, 0.4],
        "IDThreshProtocol": [0.15],
    }


def test_get_recording_protocols_reads_the_stimuli():
    client = Mock()
    client.get_entity.return_value = _recording(stimuli=["IDrest", "IDthresh_250", "Unknown"])

    out = get_recording_protocols([_RID_1, _RID_2], client)

    assert out == {
        _RID_1: ["IDRestProtocol", "IDThreshProtocol"],
        _RID_2: ["IDRestProtocol", "IDThreshProtocol"],
    }
    assert client.get_entity.call_args.args == (UUID(_RID_2),)


@pytest.mark.parametrize("label", [AssetLabel.nwb, AssetLabel.jupyter_notebook])
def test_other_assets_are_not_summaries(label):
    client = Mock()
    assert fetch_recording_summary(client, _recording(label)) is None
