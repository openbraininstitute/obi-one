import tempfile
import urllib.parse
from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.logger import L
from obi_one.scientific.library.circuit_visualization import (
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
) -> Nodes:
    asset_id = circuit_asset_id(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        parent_path = Path(temp_dir).resolve()
        config = download_circuit_config(db_client, circuit_id, asset_id, parent_path)

    return get_nodes(config, parent_path, db_client, circuit_id, asset_id)


@router.get(
    "/{circuit_id}/morphologies/{morphology_path}",
    summary="A morphology from a circuit's sonata directory",
    description="Returns a morphology for visualization",
)
def circuit_morphology(
    circuit_id: UUID,
    morphology_path: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> Morphology:
    asset_id = circuit_asset_id(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        parent_path = Path(temp_dir).resolve()
        try:
            return get_morphology(
                parent_path,
                db_client,
                circuit_id,
                asset_id,
                Path(urllib.parse.unquote(morphology_path + ".swc")),
            )
        except HTTPException:
            raise
        except Exception as e:
            L.exception(e)
            raise HTTPException(status_code=404, detail="Morphology not found") from e
