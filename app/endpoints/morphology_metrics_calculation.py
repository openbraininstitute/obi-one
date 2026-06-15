import json
import pathlib
import tempfile
import traceback
from contextlib import ExitStack, suppress
from functools import cache
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final, TypeVar, cast
from uuid import UUID

import entitysdk
from entitysdk import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import (
    BrainLocation,
    BrainRegion,
    CellMorphology,
    CellMorphologyProtocol,
    License,
    Subject,
)
from entitysdk.models.core import Identifiable
from entitysdk.models.measurement_annotation import MeasurementKind
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import app.endpoints.useful_functions.useful_functions as uf
from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.services.morphology import (
    DEFAULT_SINGLE_POINT_SOMA_BY_EXT,
    MorphologyFiles,
    validate_and_convert_morphology,
)
from app.services.morphology_registration import (
    compute_morphometrics,
    register_morphometrics,
    try_generate_and_upload_mesh,
    upload_morphology_content,
    upload_morphology_file,
)

if TYPE_CHECKING:
    from entitysdk.models.cell_morphology_protocol import CellMorphologyProtocolUnion


class ApiErrorCode:
    BAD_REQUEST = "BAD_REQUEST"
    ENTITYSDK_API_FAILURE = "ENTITYSDK_API_FAILURE"


ALLOWED_EXTENSIONS: Final[set[str]] = {".swc", ".h5", ".asc"}
ALLOWED_EXT_STR: Final[str] = ", ".join(ALLOWED_EXTENSIONS)

DEFAULT_NEURITE_DOMAIN: Final[str] = "basal_dendrite"
TARGET_NEURITE_DOMAINS: Final[list[str]] = ["apical_dendrite", "axon"]

BRAIN_LOCATION_MIN_DIMENSIONS: Final[int] = 3


router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


class MorphologyRegistrationResponse(BaseModel):
    entity_id: str
    measurement_entity_id: str
    mesh_asset_id: str | None
    status: str
    morphology_name: str


def _handle_empty_file(file: UploadFile) -> None:
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": f"Uploaded file '{file.filename}' is empty",
        },
    )


def _validate_file_extension(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"File name is missing. Must be one of {ALLOWED_EXT_STR}",
            },
        )

    file_extension = pathlib.Path(filename).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": (
                    f"Invalid file extension '{file_extension}'. Must be one of {ALLOWED_EXT_STR}"
                ),
            },
        )
    return file_extension


@cache
def _get_template() -> dict:
    template_path = Path(__file__).parent / "morphology_template.json"
    return json.loads(template_path.read_text())


@cache
def _get_analysis_dict() -> dict:
    """Lazily initialize and cache the analysis dictionary."""
    analysis_dict_base = uf.create_analysis_dict(_get_template())
    analysis_dict = dict(analysis_dict_base)

    if DEFAULT_NEURITE_DOMAIN in analysis_dict:
        default_analysis = analysis_dict[DEFAULT_NEURITE_DOMAIN]
        for domain in TARGET_NEURITE_DOMAINS:
            analysis_dict.setdefault(domain, default_analysis)

    return analysis_dict


def run_morphology_analysis(morphology_path: str) -> list[MeasurementKind]:
    try:
        return compute_morphometrics(morphology_path)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "MORPHOLOGY_ANALYSIS_ERROR",
                "detail": f"Error during morphology analysis: {e!s}",
            },
        ) from e


def _get_h5_analysis_path(
    original_file_path: str,
    file_extension: str,
    converted_files: MorphologyFiles,
) -> str:
    if file_extension == ".h5":
        return original_file_path

    if converted_files.hdf5 and converted_files.hdf5.exists():
        return str(converted_files.hdf5)

    return original_file_path


NEW_ENTITY_DEFAULTS = {
    "authorized_public": False,
    "license_id": None,
    "name": "test",
    "description": None,
    "location": None,
    "legacy_id": None,
    "brain_region_id": None,
    "subject_id": None,
    "cell_morphology_protocol_id": None,
    "repair_pipeline_state": None,
}


class MorphologyMetadata(BaseModel):
    name: str | None = None
    description: str | None = None
    license_id: str | None = None
    subject_id: str | None = None
    species_id: str | None = None
    strain_id: str | None = None
    brain_region_id: str | None = None
    repair_pipeline_state: str | None = None
    cell_morphology_protocol_id: str | None = None
    brain_location: list[float] | None = None
    authorized_public: bool = False
    published_in: str | None = None
    single_point_soma_by_ext: dict[str, bool] | None = None


async def _parse_file_and_metadata(
    file: UploadFile, metadata_str: str
) -> tuple[str, str, bytes, MorphologyMetadata]:
    morphology_name = file.filename
    file_extension = _validate_file_extension(morphology_name)
    if morphology_name is None:
        msg = "filename must not be None"
        raise AssertionError(msg)
    content = await file.read()

    if not content:
        _handle_empty_file(file)

    try:
        metadata_dict = json.loads(metadata_str) if metadata_str != "{}" else {}
        metadata_obj = MorphologyMetadata(**metadata_dict)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={"code": "INVALID_METADATA", "detail": f"Invalid metadata: {e}"},
        ) from e

    return morphology_name, file_extension, content, metadata_obj


T = TypeVar("T", bound=Identifiable)


def register_morphology(client: Client, new_item: dict[str, Any]) -> Any:
    def _get_entity(key_suffix: str, entity_class: type[T]) -> T | None:
        entity_id_key = f"{key_suffix}_id"
        entity_id = new_item.get(entity_id_key)
        if entity_id is None:
            return None

        try:
            return client.search_entity(entity_type=entity_class, query={"id": entity_id}).one()
        except EntitySDKError:
            return None

    brain_location_data = new_item.get("brain_location", [])
    brain_location: BrainLocation | None = None
    if (
        isinstance(brain_location_data, list)
        and len(brain_location_data) >= BRAIN_LOCATION_MIN_DIMENSIONS
    ):
        with suppress(TypeError, ValueError):
            brain_location = BrainLocation(
                x=float(brain_location_data[0]),
                y=float(brain_location_data[1]),
                z=float(brain_location_data[2]),
            )

    subject = _get_entity("subject", Subject)
    brain_region = _get_entity("brain_region", BrainRegion)
    morphology_protocol = _get_entity("cell_morphology_protocol", CellMorphologyProtocol)

    repair_pipeline_state = new_item.get("repair_pipeline_state")

    license = _get_entity("license", License)
    name = new_item.get("name")
    description = new_item.get("description")
    authorized_public: bool = new_item.get("authorized_public", False)
    morphology = CellMorphology(
        cell_morphology_protocol=cast("CellMorphologyProtocolUnion", morphology_protocol),
        repair_pipeline_state=repair_pipeline_state,
        name=name,
        description=description,
        subject=subject,
        license=license,
        brain_region=brain_region,
        location=brain_location,
        legacy_id=None,
        authorized_public=authorized_public,
        published_in=new_item.get("published_in"),
    )
    registered = client.register_entity(entity=morphology)
    return registered


def _raise_entitysdk_failure(operation: str, error: EntitySDKError) -> None:
    raise HTTPException(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail={
            "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
            "detail": f"Entity {operation} failed: {error}",
        },
    ) from error


def _prepare_entity_payload(
    metadata_obj: MorphologyMetadata, original_filename: str
) -> dict[str, Any]:
    entity_payload = NEW_ENTITY_DEFAULTS.copy()
    update_map = metadata_obj.model_dump(exclude_none=True)
    entity_payload.update(update_map)

    if entity_payload.get("name") in {"test", None}:
        filename_root = pathlib.Path(original_filename).stem
        entity_payload["name"] = f"Morphology: {filename_root}"

    return entity_payload


def _resolve_swc_bytes_for_mesh(
    _client: Any,
    converted_files: MorphologyFiles,
    file_extension: str,
    content: bytes,
) -> bytes | None:
    """Return the SWC bytes to use for mesh generation, or None if not applicable."""
    if converted_files.swc and converted_files.swc.exists():
        return converted_files.swc.read_bytes()
    if file_extension == ".swc":
        return content
    return None


async def _run_pipeline(
    client: Client,
    morphology_name: str,
    file_extension: str,
    content: bytes,
    entity_payload: dict[str, Any],
    single_point_soma_by_ext: dict[str, bool],
) -> tuple[str, str, str | None]:
    with ExitStack() as stack:
        temp_file_obj = stack.enter_context(
            tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        )
        temp_file_path = temp_file_obj.name
        temp_file_obj.write(content)
        temp_file_obj.close()
        stack.callback(pathlib.Path(temp_file_path).unlink, missing_ok=True)

        converted_files: MorphologyFiles = await run_in_threadpool(
            validate_and_convert_morphology,
            input_file=pathlib.Path(temp_file_path),
            output_dir=pathlib.Path(temp_file_path).parent,
            output_stem=Path(morphology_name).stem,
            single_point_soma_by_ext=single_point_soma_by_ext,
        )

        if converted_files.swc:
            stack.callback(converted_files.swc.unlink, missing_ok=True)
        if converted_files.hdf5:
            stack.callback(converted_files.hdf5.unlink, missing_ok=True)

        analysis_path = _get_h5_analysis_path(
            original_file_path=temp_file_path,
            file_extension=file_extension,
            converted_files=converted_files,
        )
        measurement_list = run_morphology_analysis(analysis_path)

        data = register_morphology(client, entity_payload)
        entity_uuid = UUID(str(data.id))
        try:
            upload_morphology_content(client, entity_uuid, morphology_name, content)
            if converted_files.swc and converted_files.swc.exists():
                upload_morphology_file(client, entity_uuid, converted_files.swc)
            if converted_files.hdf5 and converted_files.hdf5.exists():
                upload_morphology_file(client, entity_uuid, converted_files.hdf5)
            measurement_annotation = register_morphometrics(client, entity_uuid, measurement_list)
        except EntitySDKError as err:
            _raise_entitysdk_failure("registration", err)

        swc_bytes = _resolve_swc_bytes_for_mesh(client, converted_files, file_extension, content)
        mesh_asset_id: str | None = None
        if swc_bytes is not None:
            mesh_asset = await run_in_threadpool(
                lambda: try_generate_and_upload_mesh(client, entity_uuid, swc_bytes=swc_bytes)
            )
            mesh_asset_id = str(mesh_asset.id) if mesh_asset else None

        return str(entity_uuid), str(measurement_annotation.id), mesh_asset_id


@router.post(
    "/register-morphology-with-calculated-metrics",
    summary="Calculate morphology metrics and register entities.",
    description=(
        "Performs analysis on a neuron file (.swc, .h5, or .asc) and registers the entity, "
        "asset, measurements, and (when possible) a GLB surface mesh."
    ),
)
async def morphology_metrics_calculation(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    metadata: Annotated[str, Form()] = "{}",
) -> MorphologyRegistrationResponse:
    (
        morphology_name,
        file_extension,
        content,
        metadata_obj,
    ) = await _parse_file_and_metadata(file, metadata)

    entity_payload = _prepare_entity_payload(metadata_obj, morphology_name)
    single_point_soma_by_ext = (
        metadata_obj.model_dump().get("single_point_soma_by_ext")
        or DEFAULT_SINGLE_POINT_SOMA_BY_EXT
    )
    try:
        entity_id, measurement_entity_id, mesh_asset_id = await _run_pipeline(
            client=client,
            morphology_name=morphology_name,
            file_extension=file_extension,
            content=content,
            entity_payload=entity_payload,
            single_point_soma_by_ext=single_point_soma_by_ext,
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "UNEXPECTED_ERROR",
                "detail": f"Pipeline failed: {type(e).__name__} - {e!s}",
            },
        ) from e

    return MorphologyRegistrationResponse(
        entity_id=entity_id,
        measurement_entity_id=measurement_entity_id,
        mesh_asset_id=mesh_asset_id,
        status="success",
        morphology_name=morphology_name,
    )
