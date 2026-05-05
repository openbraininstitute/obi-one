from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
from fastapi import APIRouter, Depends, Path as PathParam, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import TempDirDep
from app.schemas.circuit_visualization import Sections
from app.services.circuit_visualization import (
    Nodes,
    circuit_asset_id,
    download_circuit_config,
    get_morphology,
    get_morphology_data,
    get_nodes,
)

router = APIRouter(
    prefix="/circuit/viz", tags=["visualization"], dependencies=[Depends(user_verified)]
)


@router.get(
    "/{circuit_id}/nodes",
    summary="Circuit nodes",
    description="Returns a list of all biophysical nodes for visualization",
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
    "/{circuit_id}/morphologies/{morphology_file:path}",
    summary="A morphology from a circuit's sonata directory",
    description="Returns a morphology for visualization",
)
def circuit_morphology(
    circuit_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    temp_dir: TempDirDep,
    morphology_file: Annotated[
        str, PathParam(description="The path to the morphology file. Must be URL-encoded.")
    ],
    name: Annotated[
        str | None,
        Query(
            description="The name of the morphology. Required if morphology_file is a collection."
        ),
    ] = None,
) -> Sections:
    asset_id = circuit_asset_id(db_client, circuit_id)

    morphology = get_morphology(
        temp_dir, db_client, circuit_id, asset_id, Path(morphology_file), name
    )
    return get_morphology_data(morphology)  # type: ignore ReportReturnType
