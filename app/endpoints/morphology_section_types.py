from http import HTTPStatus
from typing import Annotated, NoReturn
from uuid import UUID

import entitysdk.client
import morphio
from entitysdk.exception import EntitySDKError
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from app.schemas.morphology_section_types import (
    MorphologySectionTypeOption,
    MorphologySourceProperties,
)
from app.services.morphology_section_types import morphology_source_section_type_options

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _properties_response(
    options: list[MorphologySectionTypeOption],
) -> MorphologySourceProperties:
    return MorphologySourceProperties(section_types=options)


def _raise_discovery_error(source_id: UUID, exc: Exception) -> NoReturn:
    if isinstance(exc, EntitySDKError):
        status_code = HTTPStatus.NOT_FOUND
        code = ApiErrorCode.NOT_FOUND
    else:
        status_code = HTTPStatus.UNPROCESSABLE_ENTITY
        code = ApiErrorCode.INVALID_REQUEST

    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "detail": f"Could not discover morphology section types for {source_id}: {exc}",
        },
    ) from exc


@router.get(
    "/mapped-morphology-source-properties/{source_id}",
    summary="Mapped morphology source properties",
    description=(
        "Returns section types available in an MEModel, MEModel-with-synapses, "
        "or cell morphology source."
    ),
)
def mapped_morphology_source_properties_endpoint(
    source_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> MorphologySourceProperties:
    try:
        options = morphology_source_section_type_options(db_client, source_id)
    except (EntitySDKError, ValueError, morphio.MorphioError) as exc:
        _raise_discovery_error(source_id, exc)
    return _properties_response(options)
