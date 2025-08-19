import logging

from entitysdk.client import Client
from entitysdk.models.morphology import MTypeClass
from fastapi import APIRouter
from obi_auth import get_token
from pydantic import BaseModel

logging.basicConfig(level=logging.DEBUG)


# Define a Pydantic model for the response data
class Mty(BaseModel):
    mtype_alt_label: str
    mtype_id: str


# Create a router for your endpoints
router = APIRouter(
    prefix="/api",
    tags=["mtypes"],
)


@router.get("/mtypes")
async def get_mtype_data() -> list[Mty]:
    entitycore_api_url = "https://staging.openbraininstitute.org/api/entitycore"

    token = get_token(environment="staging")
    client = Client(api_url=entitycore_api_url, token_manager=token)

    mtypes = client.search_entity(
        entity_type=MTypeClass,
        query={},
    )

    mty_list = []
    mtype_map = {str(s.id): s.alt_label for s in mtypes}
    for mtype_id, mtype_alt_label in mtype_map.items():
        mty_list.append(Mty(mtype_alt_label=mtype_alt_label, mtype_id=mtype_id))

    return mty_list
