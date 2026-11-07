"""Tests for uploading the recording summary of an electrical cell recording."""

import json
from unittest.mock import Mock
from uuid import UUID

import pytest
from entitysdk.models import ElectricalCellRecording
from entitysdk.types import AssetLabel, ContentType

from obi_one.db_sdk.registration.electrical_cell_recording import upload_recording_summary
from obi_one.scientific.library.recording_summary import ProtocolSummary, RecordingSummary

_RECORDING_ID = UUID("00000000-0000-0000-0000-000000000001")


def _client(*existing_labels: AssetLabel) -> Mock:
    assets = []
    for i, label in enumerate(existing_labels):
        asset = Mock()
        asset.label = label
        asset.id = f"old-{i}"
        assets.append(asset)
    client = Mock()
    client.get_entity.return_value.assets = assets
    client.upload_content.return_value.id = "new"
    return client


def _summary() -> RecordingSummary:
    return RecordingSummary(
        protocols={"IDrest": ProtocolSummary(amp=[0.1])}, rheobase={"IDrest": 0.1}
    )


def test_uploads_the_summary_as_json():
    client = _client(AssetLabel.nwb)

    asset = upload_recording_summary(client, _RECORDING_ID, _summary())

    assert asset.id == "new"
    kwargs = client.upload_content.call_args.kwargs
    assert kwargs["entity_id"] == _RECORDING_ID
    assert kwargs["entity_type"] is ElectricalCellRecording
    assert kwargs["asset_label"] == AssetLabel.recording_summary
    assert kwargs["file_content_type"] == ContentType.application_json
    assert kwargs["file_name"] == "recording_summary.json"
    assert json.loads(kwargs["file_content"])["protocols"] == {"IDrest": {"amp": [0.1]}}
    client.delete_asset.assert_not_called()


def test_replaces_existing_summaries_after_uploading():
    client = _client(AssetLabel.nwb, AssetLabel.recording_summary, AssetLabel.recording_summary)
    order = Mock()
    order.attach_mock(client.upload_content, "upload")
    order.attach_mock(client.delete_asset, "delete")

    upload_recording_summary(client, _RECORDING_ID, _summary())

    assert [c[0] for c in order.mock_calls] == ["upload", "delete", "delete"]
    deleted = [c.kwargs["asset_id"] for c in client.delete_asset.call_args_list]
    assert deleted == ["old-1", "old-2"]


@pytest.mark.parametrize("admin", [False, True])
def test_admin_flag_is_passed_to_every_call(admin):
    client = _client(AssetLabel.recording_summary)

    upload_recording_summary(client, _RECORDING_ID, _summary(), admin=admin)

    assert client.get_entity.call_args.kwargs["admin"] is admin
    assert client.upload_content.call_args.kwargs["admin"] is admin
    assert client.delete_asset.call_args.kwargs["admin"] is admin
