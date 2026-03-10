from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.scientific.library.entity_property_types import IonChannelPropertyType
from obi_one.scientific.library.ion_channel_properties import get_ion_channel_variables

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/mapped-ion-channel-properties/",
    summary="Mapped ion channel properties",
    description="Returns a dictionary of mapped ion channel properties.",
)
def mapped_ion_channel_properties_endpoint(
    ion_channel_ids: list[str],
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        ion_channel_properties = get_ion_channel_variables(
            ion_channel_ids=ion_channel_ids,
            db_client=db_client,
        )
        mapped_ion_channel_properties = {}
        mapped_ion_channel_properties[IonChannelPropertyType.RECORDABLE_VARIABLES] = {
            key: value.variables_and_units for key, value in ion_channel_properties.items()
        }

    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving ion channel models among {ion_channel_ids}.",
            },
        ) from err

    return mapped_ion_channel_properties
