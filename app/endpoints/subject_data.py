from fastapi import APIRouter
from typing import List, Dict
import logging
from pydantic import BaseModel
import jsonpickle

from entitysdk.client import Client
from entitysdk.common import ProjectContext
from entitysdk.models.morphology import Species, Strain
from obi_auth import get_token

logging.basicConfig(level=logging.DEBUG)

# Define a Pydantic model for the response data
class Spec(BaseModel):
    species_name: str
    species_id: str
    strains: Dict[str, str]

# Create a router for your endpoints
router = APIRouter(
    prefix="/api",
    tags=["subject_data"],
)

@router.get("/subject_data", response_model=List[Spec])
async def get_subject_data():
    entitycore_api_url = "https://staging.openbraininstitute.org/api/entitycore"
    project_context = ProjectContext(
        virtual_lab_id="bf7d398c-b812-408a-a2ee-098f633f7798",
        project_id="efb206e6-ba4e-4f2f-88f0-3ff5d9e98921",
    )
    token = get_token(environment="staging")
    client = Client(api_url=entitycore_api_url, project_context=project_context,token_manager=token)

    species = client.search_entity(
        entity_type=Species, query={},  limit=10
    )
    strains = client.search_entity(entity_type=Strain, query={})

    spec_list = []
    species_map = {str(s.id): s.name for s in species}

    for species_id, species_name in species_map.items():
        spec_list.append(Spec(species_name=species_name, species_id=species_id, strains={}))

    for strain in strains:
        for spec in spec_list:
            if str(strain.species_id) == spec.species_id:
                spec.strains[strain.name] = str(strain.id)
    
    return spec_list