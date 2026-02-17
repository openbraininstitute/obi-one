from http import HTTPStatus
from typing import Annotated
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from entitysdk.models import (
    CellMorphology,
    BrainLocation,
    BrainRegion,
    Contribution,
    MTypeClass,
    MTypeClassification,
    Organization,
    CellMorphologyProtocol,
    Species,
    Strain,
)
from entitysdk.client import Client

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode

router = APIRouter(prefix="/entities", tags=["entities"], dependencies=[Depends(user_verified)])

# --- Enumerations and Mappings ---

class EntityTypeName(str, Enum):
    cell_morphology = "cell_morphology"
    brain_location = "brain_location"
    brain_region = "brain_region"
    contribution = "contribution"
    m_type_class = "m_type_class"
    m_type_classification = "m_type_classification"
    organization = "organization"
    cell_morphology_protocol = "cell_morphology_protocol"
    species = "species"
    strain = "strain"

ENTITY_TYPE_MAP = {
    EntityTypeName.cell_morphology: CellMorphology,
    EntityTypeName.brain_location: BrainLocation,
    EntityTypeName.brain_region: BrainRegion,
    EntityTypeName.contribution: Contribution,
    EntityTypeName.m_type_class: MTypeClass,
    EntityTypeName.m_type_classification: MTypeClassification,
    EntityTypeName.organization: Organization,
    EntityTypeName.cell_morphology_protocol: CellMorphologyProtocol,
    EntityTypeName.species: Species,
    EntityTypeName.strain: Strain,
}

# --- Endpoint ---

@router.get("/{entity_type_name}/{entity_id}/check-public")
def check_if_entity_can_be_made_public(
    entity_type_name: EntityTypeName,
    entity_id: Annotated[str, PathParam(...)],
    client: Annotated[Client, Depends(get_client)],
) -> dict:
    sdk_type = ENTITY_TYPE_MAP.get(entity_type_name)

    # 1. Fetch the entity
    try:
        fetched = client.get_entity(entity_id=entity_id, entity_type=sdk_type)
    except Exception as e:
        error_str = str(e)
        if "401" in error_str:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": "SDK authentication failed (401 Unauthorized).",
                },
            )
        if "403" in error_str:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": f"Access denied to entity {entity_id}.",
                },
            )
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Entity {entity_id} of type {entity_type_name.value} not found.",
            },
        )

    # 2. Check if already public
    if fetched.authorized_public:
        return {"can_be_made_public": False, "reason": "Entity is already public."}

    # 3. Check for license
    if getattr(fetched, "license", None) is None:
        return {"can_be_made_public": False, "reason": "Entity missing required license."}

    # 4. Filter out test entities
    name = getattr(fetched, "name", "")
    if "test" in name.lower():
        return {"can_be_made_public": False, "reason": "Test entities cannot be made public."}

    # 5. Check for duplicate public names
    try:
        found_entities = client.search_entity(entity_type=sdk_type, query={"name": name}, limit=10)
        for item in found_entities:
            if item.authorized_public:
                return {
                    "can_be_made_public": False,
                    "reason": "An entity with this name is already public.",
                }
    except Exception:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Failed to perform duplicate check database query.",
            },
        )

    return {"can_be_made_public": True}