from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.scientific.library.electrical_cell_recording_properties import (
    get_recording_protocols,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


class ElectricalCellRecordingProtocolsResponse(BaseModel):
    """Protocols available across a set of ElectricalCellRecording entities."""

    by_recording: dict[str, list[str]] = Field(
        description="Mapping of recording id to the list of protocol (ecode) names in its NWB.",
    )
    union: list[str] = Field(
        description="Sorted union of protocol (ecode) names across all requested recordings.",
    )


@router.get(
    "/electrical-cell-recording-protocols",
    summary="ElectricalCellRecording protocols",
    description=(
        "Inspect the NWB asset of each requested ``ElectricalCellRecording`` and"
        " return the protocols (ecodes) it contains, both per-recording and as the"
        " union across all requested recordings."
    ),
)
def electrical_cell_recording_protocols_endpoint(
    recording_ids: Annotated[list[str], Query()],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> ElectricalCellRecordingProtocolsResponse:
    try:
        by_recording = get_recording_protocols(
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
    return ElectricalCellRecordingProtocolsResponse(by_recording=by_recording, union=union)
