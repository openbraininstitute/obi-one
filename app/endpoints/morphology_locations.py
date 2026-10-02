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
from app.logger import L
from app.schemas.morphology_locations import MorphologyLocation, MorphologyLocationsPreview
from app.services.morphology_locations import preview_morphology_locations
from obi_one.core.exception import OBIONEError
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationUnion,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _raise_preview_error(entity_id: UUID, exc: Exception) -> NoReturn:
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
            "detail": f"Could not preview morphology locations for {entity_id}: {exc}",
        },
    ) from exc


@router.post(
    "/morphology-locations/preview/{entity_id}",
    summary="Morphology-locations preview",
    description=(
        "Return the locations a morphology-location block generates on the morphology of an "
        "MEModel, single-neuron circuit, or cell morphology, so they can be shown in the 3D "
        "viewer before the workflow runs. Each location carries the SONATA `section_id` and "
        "`offset` the block would write to `compartment_sets.json`. Applied to a neuron set, the "
        "block samples every targeted morphology independently, so a preview against one "
        "morphology is representative rather than the exact set of rows that will be persisted."
    ),
)
def morphology_locations_preview_endpoint(
    entity_id: UUID,
    morphology_locations: MorphologyLocationUnion,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> MorphologyLocationsPreview:
    L.info("morphology_locations_preview_endpoint")
    try:
        rows = preview_morphology_locations(db_client, entity_id, morphology_locations)
    except TypeError as exc:
        # points_on rejects parameter sweeps; a preview needs one resolved value per parameter.
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": (
                    "All parameters must be single values; parameter-sweep lists are not supported."
                ),
            },
        ) from exc
    except (EntitySDKError, OBIONEError, ValueError, KeyError, morphio.MorphioError) as exc:
        _raise_preview_error(entity_id, exc)

    return MorphologyLocationsPreview(
        locations=[
            MorphologyLocation(section_id=section_id, offset=offset) for section_id, offset in rows
        ]
    )
