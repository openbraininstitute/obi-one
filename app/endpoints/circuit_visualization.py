from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
from fastapi import APIRouter, Depends

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import TempDirDep
from app.services.circuit_visualization import (
    Morphology,
    Nodes,
    circuit_asset_id,
    download_circuit_config,
    get_morphology,
    get_nodes,
)

router = APIRouter(
    prefix="/circuit/viz", tags=["visualization"], dependencies=[Depends(user_verified)]
)


@router.get(
    "/{circuit_id}/nodes",
    summary="Circuit nodes",
    description="Returns a list of nodes for visualization",
)
def circuit_nodes(
    circuit_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    temp_dir: TempDirDep,
) -> Nodes:
    asset_id = circuit_asset_id(db_client, circuit_id)

    config = download_circuit_config(db_client, circuit_id, asset_id, temp_dir)

    return get_nodes(config, temp_dir, db_client, circuit_id, asset_id)


@router.get(
    "/{circuit_id}/morphologies/{morphology_path:path}",
    summary="A morphology from a circuit's sonata directory",
    description="Returns a morphology for visualization",
)
def circuit_morphology(
    circuit_id: UUID,
    morphology_path: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    temp_dir: TempDirDep,
) -> Morphology:
    asset_id = circuit_asset_id(db_client, circuit_id)

    return get_morphology(
        temp_dir,
        db_client,
        circuit_id,
        asset_id,
        Path(morphology_path + ".swc"),
    )
