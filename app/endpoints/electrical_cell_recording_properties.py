from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.scientific.library.entity_property_types import (
    ElectricalCellRecordingMappedProperties,
)
from obi_one.utils.db_sdk import get_recording_amplitudes, get_recording_protocols

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/mapped-electrical-cell-recording-properties",
    summary="Mapped electrical cell recording properties",
    description=(
        "Return a dictionary of mapped ``ElectricalCellRecording`` properties for the"
        " requested recordings, keyed by ``ElectricalCellRecordingMappedProperties``: the"
        " protocol (ecode) names per recording and their union, plus the per-protocol step"
        " amplitudes (nA) discovered from the recordings' NWBs."
    ),
)
def mapped_electrical_cell_recording_properties_endpoint(
    recording_ids: Annotated[list[str], Query()],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        by_recording = get_recording_protocols(
            recording_ids=recording_ids,
            db_client=db_client,
        )
        amplitudes_by_protocol = get_recording_amplitudes(
            recording_ids=recording_ids,
            db_client=db_client,
        )
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

    union = sorted({p for protocols in by_recording.values() for p in protocols})
    return {
        ElectricalCellRecordingMappedProperties.PROTOCOLS: union,
        ElectricalCellRecordingMappedProperties.PROTOCOLS_BY_RECORDING: by_recording,
        ElectricalCellRecordingMappedProperties.AMPLITUDES_BY_PROTOCOL: amplitudes_by_protocol,
    }
