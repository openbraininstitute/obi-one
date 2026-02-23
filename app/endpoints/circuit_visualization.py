from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk.client
import entitysdk.exception
from entitysdk.client import Client
from entitysdk.common import ProjectContext
from entitysdk.models import Circuit
from fastapi import APIRouter, Depends, HTTPException, Query
from pathlib import Path
import os
import tempfile

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from app.logger import L
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsOutput,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)

from bluepysnap import Circuit as CircuitConfig
from bluepysnap.exceptions import BluepySnapError
from pathlib import Path

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
):
    asset_id = circuit_asset_id(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        config = download_circuit_config(db_client, circuit_id, asset_id, temp_dir)

        for node_network in config.config["networks"]["nodes"]:
            for pop_name, pop_config in node_network["populations"].items():
                if pop_config.get("type") != "biophysical":
                    continue

                nodes_file_path = Path(node_network["nodes_file"]).resolve()
                parent_path = Path(temp_dir).resolve()
                asset_path = nodes_file_path.relative_to(parent_path)

                try:
                    db_client.download_file(
                        entity_id=circuit_id,
                        entity_type=Circuit,
                        asset_id=asset_id,
                        output_path=nodes_file_path,
                        asset_path=asset_path,
                    )
                except Exception:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail={
                            "code": ApiErrorCode.INVALID_REQUEST,
                            "detail": f"Missing file {asset_path}",
                        },
                    ) from None


def circuit_asset_id(client: Client, circuit_id: UUID) -> UUID:
    try:
        circuit = client.get_entity(entity_id=circuit_id, entity_type=Circuit)
    except Exception as e:  # noqa:BLE001
        L.exception(e)
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "code": ApiErrorCode.NOT_FOUND,
                "detail": "Circuit not found",
            },
        ) from None

    if circuit.scale not in {"small", "pair"}:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit's scale should be 'small' or 'pair'",
            },
        )

    asset = next((a for a in circuit.assets if a.label == "sonata_circuit"), None)

    if asset is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit is missing a sonata_circuit asset",
            },
        )

    return asset.id


def download_circuit_config(
    client: Client, circuit_id: UUID, asset_id: UUID, directory: str
) -> CircuitConfig:
    circuit_config = Path("circuit_config.json")

    try:
        file_path = Path(directory) / circuit_config

        client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=file_path,
            asset_path=circuit_config,
        )

        return CircuitConfig(file_path)

    except BluepySnapError:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid circuit configuration",
            },
        ) from None

    except Exception:  # noqa:BLE001
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Circuit is missing a circuit__config.json asset",
            },
        ) from None
