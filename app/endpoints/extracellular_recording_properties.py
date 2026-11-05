from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk.client
import entitysdk.exception
import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.core.exception import OBIONEError
from obi_one.db_sdk.db_sdk import get_extracellular_recording_channel_options
from obi_one.scientific.library.entity_property_types import (
    ExtracellularRecordingMappedProperties,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/mapped-extracellular-recording-properties/{recording_id}",
    summary="Mapped extracellular recording properties",
    description=(
        "Returns a dictionary of mapped ``ExtracellularRecording`` properties: the raw channels"
        " of its NWB file, read without downloading the file."
    ),
)
def mapped_extracellular_recording_properties_endpoint(
    recording_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        channels = get_extracellular_recording_channel_options(
            recording_id=recording_id, db_client=db_client
        )
    except (
        entitysdk.exception.EntitySDKError,
        OBIONEError,
        httpx.HTTPError,
        OSError,
        KeyError,
    ) as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Could not read the channels of recording {recording_id}: {err}",
            },
        ) from err
    return {ExtracellularRecordingMappedProperties.CHANNELS: channels, "usability": {}}
