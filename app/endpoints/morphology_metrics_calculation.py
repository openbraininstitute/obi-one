import json
import pathlib
import tempfile
import traceback
import uuid
from contextlib import ExitStack, suppress
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Final, TypeVar

import entitysdk
import neurom as nm
import requests
from entitysdk import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import (
    BrainLocation,
    BrainRegion,
    CellMorphology,
    CellMorphologyProtocol,
    License,
    MeasurementAnnotation,
    Subject,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from requests.exceptions import RequestException

import app.endpoints.useful_functions.useful_functions as uf
from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.convert_morphology_to_registered_mesh import (
    HAS_MESHING,
    mesh_and_register as _mesh_and_register,
)
from app.errors import ApiError
from app.logger import L
from app.services.morphology import (
    DEFAULT_SINGLE_POINT_SOMA_BY_EXT,
    MorphologyFiles,
    validate_and_convert_morphology,
)


class ApiErrorCode:
    BAD_REQUEST = "BAD_REQUEST"
    ENTITYSDK_API_FAILURE = "ENTITYSDK_API_FAILURE"


class BaseEntity:
    def __init__(self, entity_id: Any | None = None) -> None:
        """Initialize the base entity."""


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


def _get_template() -> dict:
    if hasattr(_get_template, "cached"):
        return _get_template.cached

    template_path = Path(__file__).parent / "morphology_template.json"
    template = json.loads(template_path.read_text())

    _get_template.cached = template  # ty:ignore[unresolved-attribute]
    return template


def _get_analysis_dict() -> dict:
    """Lazily initialize and cache the analysis dictionary."""
    if hasattr(_get_analysis_dict, "cached"):
        return _get_analysis_dict.cached

    analysis_dict_base = uf.create_analysis_dict(_get_template())
    analysis_dict = dict(analysis_dict_base)

    if DEFAULT_NEURITE_DOMAIN in analysis_dict:
        default_analysis = analysis_dict[DEFAULT_NEURITE_DOMAIN]
        for domain in TARGET_NEURITE_DOMAINS:
            analysis_dict.setdefault(domain, default_analysis)

    _get_analysis_dict.cached = analysis_dict  # ty:ignore[unresolved-attribute]
    return analysis_dict


def run_morphology_analysis(morphology_path: str) -> list[dict[str, Any]]:
    try:
        neuron = nm.load_morphology(morphology_path)
        results_dict = uf.build_results_dict(_get_analysis_dict(), neuron)
        filled = uf.fill_json(_get_template(), results_dict, entity_id="temp_id")
        measurement_kinds = filled["data"][0]["measurement_kinds"]
        filled["data"][0]["measurement_kinds"] = [
            mk
            for mk in measurement_kinds
            if any(mi.get("value") is not None for mi in mk.get("measurement_items", []))
        ]
        return filled["data"][0]["measurement_kinds"]
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
    converted_hdf5_path: str | None,
    converted_swc_path: str | None,  # noqa: ARG001 (kept for symmetry / future use)
) -> str:
    if file_extension == ".h5":
        return original_file_path

    if converted_hdf5_path and pathlib.Path(converted_hdf5_path).exists():
        return converted_hdf5_path

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

    return morphology_name, file_extension, content, metadata_obj  # ty:ignore[invalid-return-type]


T = TypeVar("T", bound=BaseEntity)


def register_morphology(client: Client, new_item: dict[str, Any]) -> Any:
    def _get_entity(key_suffix: str, entity_class: type[T]) -> T | None:
        entity_id_key = f"{key_suffix}_id"
        entity_id = new_item.get(entity_id_key)
        if entity_id is None:
            return None

        try:
            return client.search_entity(entity_type=entity_class, query={"id": entity_id}).one()  # ty:ignore[invalid-argument-type]
        except (EntitySDKError, RequestException):
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

    subject = _get_entity("subject", Subject)  # ty:ignore[invalid-argument-type]
    brain_region = _get_entity("brain_region", BrainRegion)  # ty:ignore[invalid-argument-type]
    morphology_protocol = _get_entity("cell_morphology_protocol", CellMorphologyProtocol)  # ty:ignore[invalid-argument-type]
    repair_pipeline_state = new_item.get("repair_pipeline_state")

    license = _get_entity("license", License)  # ty:ignore[invalid-argument-type]
    name = new_item.get("name")
    description = new_item.get("description")
    authorized_public = new_item.get("authorized_public")
    morphology = CellMorphology(
        cell_morphology_protocol=morphology_protocol,  # ty:ignore[invalid-argument-type]
        repair_pipeline_state=repair_pipeline_state,
        name=name,
        description=description,
        subject=subject,
        license=license,
        brain_region=brain_region,
        location=brain_location,
        legacy_id=None,
        authorized_public=authorized_public,  # ty:ignore[invalid-argument-type]
        published_in=new_item.get("published_in"),
    )
    registered = client.register_entity(entity=morphology)
    return registered


EXTENSION_MIME_MAP: Final[dict[str, str]] = {
    ".asc": "application/asc",
    ".swc": "application/swc",
    ".h5": "application/x-hdf5",
}


def _get_mime_type(file_extension: str) -> str:
    mime_type = EXTENSION_MIME_MAP.get(file_extension.lower())
    if not mime_type:
        error_msg = f"Unsupported file extension: '{file_extension}'."
        raise ValueError(error_msg)
    return mime_type


def register_asset_from_content(
    client: Client,
    entity_id: str,
    morphology_name: str,
    content: bytes,
) -> dict[str, Any]:
    file_extension = pathlib.Path(morphology_name).suffix
    mime_type = _get_mime_type(file_extension)
    try:
        asset = client.upload_content(
            entity_id=entity_id,
            entity_type=CellMorphology,
            file_content=content,
            file_name=morphology_name,
            file_content_type=mime_type,
            asset_label="morphology",
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"Entity asset registration failed: {e}",
            },
        ) from e
    else:
        return asset  # ty:ignore[invalid-return-type]


def register_assets(
    client: Client,
    entity_id: str,
    file_folder: str,
    morphology_name: str,
) -> dict[str, Any]:
    file_path = pathlib.Path(file_folder) / morphology_name

    if not file_path.exists():
        error_msg = f"Asset file not found at path: {file_path}"
        raise FileNotFoundError(error_msg)

    mime_type = _get_mime_type(file_path.suffix)

    try:
        asset1 = client.upload_file(
            entity_id=entity_id,  # ty:ignore[invalid-argument-type]
            entity_type=CellMorphology,
            file_path=str(file_path),  # ty:ignore[invalid-argument-type]
            file_content_type=mime_type,  # ty:ignore[invalid-argument-type]
            asset_label="morphology",  # ty:ignore[invalid-argument-type]
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"Entity asset registration failed: {e}",
            },
        ) from e
    else:
        return asset1  # ty:ignore[invalid-return-type]


def register_measurements(
    client: Client,
    entity_id: str,
    measurements: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        measurement_annotation = MeasurementAnnotation(
            entity_id=entity_id,  # ty:ignore[invalid-argument-type]
            entity_type="cell_morphology",  # ty:ignore[invalid-argument-type]
            measurement_kinds=measurements,  # ty:ignore[invalid-argument-type]
        )
        registered = client.register_entity(entity=measurement_annotation)
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"Entity measurement registration failed: {e}",
            },
        ) from e
    else:
        return registered  # ty:ignore[invalid-return-type]


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


def _register_assets_and_measurements(
    client: Client,
    entity_id: str,
    morphology_name: str,
    content: bytes,
    measurement_list: list[dict[str, Any]],
    converted_swc_path: str | None,
    converted_hdf5_path: str | None,
) -> dict[str, Any]:
    register_asset_from_content(client, entity_id, morphology_name, content)

    if converted_swc_path:
        swc = pathlib.Path(converted_swc_path)
        if swc.exists():
            register_assets(client, entity_id, str(swc.parent), swc.name)

    if converted_hdf5_path:
        hdf5 = pathlib.Path(converted_hdf5_path)
        if hdf5.exists():
            register_assets(client, entity_id, str(hdf5.parent), hdf5.name)

    registered = register_measurements(client, entity_id, measurement_list)
    return registered


def _resolve_swc_bytes_for_mesh(
    _client: Any,
    converted_swc_path: str | None,
    file_extension: str,
    content: bytes,
) -> bytes | None:
    """Return the SWC bytes to use for mesh generation, or None if not applicable."""
    if converted_swc_path:
        swc = Path(converted_swc_path)
        if swc.exists():
            return swc.read_bytes()
    if file_extension == ".swc":
        return content
    return None


def _try_mesh_and_register(
    client: entitysdk.client.Client,
    entity_id: str,
    swc_bytes: bytes,
) -> str | None:
    if not HAS_MESHING:
        L.info("_try_mesh_and_register: meshing dependencies not available, skipping")
        return None
    try:
        asset = _mesh_and_register(client, uuid.UUID(entity_id), swc_bytes)
        return str(asset.id)
    except ApiError as err:
        L.warning(f"_try_mesh_and_register: meshing failed for {entity_id}: {err.message}")
        return None
    except Exception as err:  # noqa: BLE001
        L.warning(f"_try_mesh_and_register: unexpected meshing error for {entity_id}: {err}")
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

        converted_swc = str(converted_files.swc) if converted_files.swc else None
        converted_hdf5 = str(converted_files.hdf5) if converted_files.hdf5 else None

        if converted_files.swc:
            stack.callback(converted_files.swc.unlink, missing_ok=True)
        if converted_files.hdf5:
            stack.callback(converted_files.hdf5.unlink, missing_ok=True)

        analysis_path = _get_h5_analysis_path(
            original_file_path=temp_file_path,
            file_extension=file_extension,
            converted_hdf5_path=converted_hdf5,
            converted_swc_path=converted_swc,
        )
        measurement_list = run_morphology_analysis(analysis_path)

        data = register_morphology(client, entity_payload)
        entity_id = str(data.id)
        data2 = _register_assets_and_measurements(
            client,
            entity_id,
            morphology_name,
            content,
            measurement_list,
            converted_swc,
            converted_hdf5,
        )

        swc_bytes = _resolve_swc_bytes_for_mesh(client, converted_swc, file_extension, content)
        mesh_asset_id: str | None = None
        if swc_bytes is not None:
            mesh_asset_id = await run_in_threadpool(
                _try_mesh_and_register, client, entity_id, swc_bytes
            )

        return entity_id, str(data2.id), mesh_asset_id  # ty:ignore[unresolved-attribute]


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
