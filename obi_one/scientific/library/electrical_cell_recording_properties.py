"""Helpers for inspecting ``ElectricalCellRecording`` entities.

Currently exposes the set of protocol names present in each recording's NWB
asset, which the e-feature extraction stage uses to drive ``ExtractionTargets``.
"""

import logging
import tempfile
from pathlib import Path

import entitysdk.client
import h5py
from entitysdk.models import ElectricalCellRecording
from entitysdk.types import ContentType

L = logging.getLogger(__name__)


def _read_protocols_from_nwb(nwb_path: Path) -> list[str]:
    """Return the sorted protocol (ecode) names stored in an NWB file.

    For BBP-style NWBs the protocol names live under ``data_organization/<cell>/<ecode>``.
    For other formats we fall back to parsing the ``ccs__<ECODE>__<idx>`` /
    ``ic__<ECODE>__<idx>`` keys in ``acquisition``.
    """
    min_parts_for_protocol = 2
    protocols: set[str] = set()
    with h5py.File(str(nwb_path), "r") as f:
        if "data_organization" in f:
            for cell_id in f["data_organization"]:
                protocols.update(f["data_organization"][cell_id].keys())
        elif "acquisition" in f:
            for key in f["acquisition"]:
                parts = key.split("__")
                if len(parts) >= min_parts_for_protocol:
                    protocols.add(parts[1])
    return sorted(protocols)


def get_recording_protocols(
    recording_ids: list[str],
    db_client: entitysdk.client.Client,
) -> dict[str, list[str]]:
    """Return ``{recording_id: [protocol_name, ...]}`` for each NWB asset."""
    result: dict[str, list[str]] = {}
    for rid in recording_ids:
        entity = db_client.get_entity(entity_id=rid, entity_type=ElectricalCellRecording)
        with tempfile.NamedTemporaryFile(suffix=".nwb") as tmp:
            for asset in entity.assets:
                if asset.content_type == ContentType.application_nwb:
                    content = db_client.download_content(
                        entity_id=rid,  # ty:ignore[invalid-argument-type]
                        entity_type=ElectricalCellRecording,
                        asset_id=asset.id,
                    )
                    tmp.write(content)
                    tmp.flush()
                    break
            else:
                msg = f"No asset with content type 'application/nwb' found for recording {rid}."
                raise ValueError(msg)
            result[rid] = _read_protocols_from_nwb(Path(tmp.name))
    return result
