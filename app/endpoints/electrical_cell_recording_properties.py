from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk.client
import entitysdk.exception
from entitysdk.models import ElectricalCellRecording
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.db_sdk.db_sdk import (
    amplitudes_by_protocol_class,
    compute_recording_summary_from_nwb,
    get_electrical_cell_recordings,
    get_recording_summary,
    recording_protocol_classes,
)
from obi_one.scientific.library.entity_property_types import (
    ElectricalCellRecordingMappedProperties,
)
from obi_one.scientific.library.recording_summary import (
    RecordingSummary,
    relative_amplitudes_by_class,
    rheobase_protocol_classes,
    timing_by_class,
)

# Rheobase protocol the % amplitudes are relative to unless the request names others:
# the extraction settings' default.
DEFAULT_RHEOBASE_PROTOCOLS = ["IDThreshProtocol"]

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/mapped-electrical-cell-recording-properties",
    summary="Mapped electrical cell recording properties",
    description=(
        "Return a dictionary of mapped ``ElectricalCellRecording`` properties for the"
        " requested recordings, keyed by ``ElectricalCellRecordingMappedProperties``: the"
        " protocol types per recording and their union; the per-protocol amplitudes (nA)"
        " and detected stimulus timing (ms); the protocols that can give a rheobase; and,"
        " for the ``rheobase_protocols`` (``Protocol`` type names, default"
        " IDThreshProtocol), each recording's rheobase and the per-protocol amplitudes as"
        " % of it. With several rheobase protocols, a recording's rheobase is the smallest"
        " of theirs, as bluepyefe computes it; it is null when none fires, or one fires at"
        " 0 nA or below. Everything comes from each recording's ``recording_summary``"
        " asset; a recording without one has its NWB file downloaded and parsed instead."
    ),
)
def mapped_electrical_cell_recording_properties_endpoint(
    recording_ids: Annotated[list[str], Query()],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    rheobase_protocols: Annotated[list[str] | None, Query()] = None,
) -> dict:
    try:
        recordings = get_electrical_cell_recordings(recording_ids, db_client)
        summaries = {
            rid: get_recording_summary(db_client, recording)
            for rid, recording in recordings.items()
        }
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": (
                    f"Internal error retrieving electrical cell recordings among {recording_ids}."
                ),
            },
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": str(err),
            },
        ) from err

    by_recording = {
        rid: recording_protocol_classes(recording) for rid, recording in recordings.items()
    }
    union = sorted({p for protocols in by_recording.values() for p in protocols})
    rheobase_from = rheobase_protocols or DEFAULT_RHEOBASE_PROTOCOLS
    return {
        ElectricalCellRecordingMappedProperties.PROTOCOLS: union,
        ElectricalCellRecordingMappedProperties.PROTOCOLS_BY_RECORDING: by_recording,
        ElectricalCellRecordingMappedProperties.AMPLITUDES_BY_PROTOCOL: (
            amplitudes_by_protocol_class(summaries)
        ),
        ElectricalCellRecordingMappedProperties.TIMING_BY_PROTOCOL: timing_by_class(summaries),
        ElectricalCellRecordingMappedProperties.RHEOBASE_PROTOCOLS: (
            rheobase_protocol_classes(summaries)
        ),
        ElectricalCellRecordingMappedProperties.RELATIVE_AMPLITUDES_BY_PROTOCOL: (
            relative_amplitudes_by_class(summaries, rheobase_from)
        ),
        ElectricalCellRecordingMappedProperties.RHEOBASE_BY_RECORDING: {
            rid: summary.rheobase_for(rheobase_from) if summary else None
            for rid, summary in summaries.items()
        },
    }


@router.get(
    "/electrical-cell-recording-summary",
    summary="Electrical cell recording summary",
    description=(
        "Compute the ``recording_summary`` of an ``ElectricalCellRecording`` from its NWB"
        " file: the distinct amplitudes (nA) and stimulus timing (ms) of each current-clamp"
        " protocol, and the rheobase of each step protocol. The result is returned, not"
        " stored; it is what the recording's"
        " ``recording_summary`` asset holds. The NWB file is downloaded and parsed on"
        " every call."
    ),
)
def electrical_cell_recording_summary_endpoint(
    recording_id: Annotated[UUID, Query()],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> RecordingSummary:
    try:
        recording = db_client.get_entity(recording_id, entity_type=ElectricalCellRecording)
        summary = compute_recording_summary_from_nwb(db_client, recording)
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving electrical cell recording {recording_id}.",
            },
        ) from err
    if summary is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "code": ApiErrorCode.NOT_FOUND,
                "detail": f"Electrical cell recording {recording_id} has no NWB asset.",
            },
        )
    return summary
