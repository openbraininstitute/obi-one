"""Upload the recording summary of an electrical cell recording."""

import logging
from uuid import UUID

from entitysdk import Client
from entitysdk.models import ElectricalCellRecording
from entitysdk.models.asset import Asset
from entitysdk.types import AssetLabel, ContentType

from obi_one.scientific.library.recording_summary import (
    RECORDING_SUMMARY_FILE_NAME,
    RecordingSummary,
)

L = logging.getLogger(__name__)


def upload_recording_summary(
    client: Client,
    recording_id: UUID,
    summary: RecordingSummary,
    *,
    admin: bool = False,
) -> Asset:
    """Upload ``summary`` as the recording's ``recording_summary`` asset.

    Replaces any existing summary: entitycore accepts several assets with the same
    label, so the new one is uploaded first and the previous ones are deleted
    after it, leaving the recording with exactly one summary. ``admin`` uses the
    admin routes, which public recordings need.
    """
    recording = client.get_entity(recording_id, entity_type=ElectricalCellRecording, admin=admin)
    previous = [a for a in recording.assets or [] if a.label == AssetLabel.recording_summary]
    asset = client.upload_content(
        entity_id=recording_id,
        entity_type=ElectricalCellRecording,
        file_content=summary.model_dump_json().encode(),
        file_name=RECORDING_SUMMARY_FILE_NAME,
        file_content_type=ContentType.application_json,
        asset_label=AssetLabel.recording_summary,
        admin=admin,
    )
    for old in previous:
        client.delete_asset(
            entity_id=recording_id,
            entity_type=ElectricalCellRecording,
            asset_id=old.id,
            admin=admin,
        )
        L.info("Replaced recording summary %s of %s with %s", old.id, recording_id, asset.id)
    return asset
