from http import HTTPStatus
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import entitysdk.client
import morphio
from entitysdk.exception import EntitySDKError
from entitysdk.models import MEModel
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Response

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import TempDirDep
from app.errors import ApiErrorCode
from app.schemas.circuit_visualization import Sections, SynapseGroups
from app.services.circuit_morphology_pack import (
    DEFAULT_MAX_SEGMENTS,
    build_circuit_morphology_pack,
)
from app.services.circuit_visualization import (
    Nodes,
    circuit_asset_id,
    download_circuit_config,
    get_afferent_synapses,
    get_morphology,
    get_morphology_data,
    get_nodes,
    load_memodel_morphology,
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


@router.get(
    "/{circuit_id}/morphology-pack",
    summary="Circuit morphologies as one pack",
    description=(
        "Returns the morphologies of every biophysical neuron of a circuit as one binary pack: "
        "simplified, placed in the circuit and cut into chunks of space. The format is specified "
        "in `docs/internal/circuit-morphology-pack.md`. The pack holds one level of detail, the "
        "finest that comes to at most `max_segments` segments, or with `all_levels` every level, "
        "as a pack stored on the circuit is to. It is built in the request, so a circuit too "
        "large for that is refused, with a `reason`. Temporary: to be removed once circuit "
        "registration stores the pack on the circuit."
    ),
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        422: {"description": "The circuit is too large for a request, or has no morphologies."},
        503: {"description": "Another pack is being built."},
    },
)
def circuit_morphology_pack(
    circuit_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    temp_dir: TempDirDep,
    max_segments: Annotated[
        int, Query(ge=1, description="The most segments the viewer can draw.")
    ] = DEFAULT_MAX_SEGMENTS,
    all_levels: Annotated[  # ruff: ignore[boolean-default-value-positional-argument]
        bool, Query(description="Every level of detail, finest first. `max_segments` is not used.")
    ] = False,
) -> Response:
    pack = build_circuit_morphology_pack(
        db_client, circuit_id, temp_dir, max_segments, all_levels=all_levels
    )
    return Response(content=pack, media_type="application/octet-stream")


@router.get(
    "/{circuit_id}/synapses",
    summary="Circuit afferent synapses",
    description=(
        "Returns afferent synapse positions per edge population, for drawing on the morphology. "
        "Populations recording connectivity without geometry are omitted, so an empty list "
        "means there is nothing to draw rather than a failure."
    ),
    responses={400: {"description": "An edge file path escapes the circuit directory."}},
)
def circuit_synapses(
    circuit_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    temp_dir: TempDirDep,
) -> SynapseGroups:
    asset_id = circuit_asset_id(db_client, circuit_id)
    config = download_circuit_config(db_client, circuit_id, asset_id, temp_dir)
    return get_afferent_synapses(  # type: ignore ReportReturnType
        config, temp_dir, db_client, circuit_id, asset_id
    )


memodel_router = APIRouter(
    prefix="/memodel/viz", tags=["visualization"], dependencies=[Depends(user_verified)]
)


def _raise_morphology_error(memodel_id: UUID, exc: Exception) -> NoReturn:
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
            "detail": f"Could not load the morphology of MEModel {memodel_id}: {exc}",
        },
    ) from exc


@memodel_router.get(
    "/{memodel_id}/morphology",
    summary="An MEModel's morphology",
    description=(
        "Returns an MEModel's morphology for visualization, in the same shape as "
        "`/circuit/viz/{circuit_id}/morphologies/{morphology_file}`. An MEModel is a single "
        "neuron and is not stored as a Circuit, so it is served from its cell morphology asset "
        "rather than from a SONATA circuit."
    ),
    responses={
        404: {"description": "No such MEModel."},
        422: {"description": "The MEModel has no morphology asset that can be read."},
    },
)
def memodel_morphology(
    memodel_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> Sections:
    try:
        memodel = db_client.get_entity(entity_id=memodel_id, entity_type=MEModel)
        morphology = load_memodel_morphology(db_client, memodel)
    except (EntitySDKError, ValueError, morphio.MorphioError) as exc:
        _raise_morphology_error(memodel_id, exc)
    return get_morphology_data(morphology)  # type: ignore ReportReturnType
