import json
import pathlib
import tempfile
import traceback
from contextlib import ExitStack, suppress
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Final, TypeVar
from uuid import UUID

# --- Heavy third-party imports (top-level, used lazily) ---
import neurom as nm

# --- Standard & project imports ---
import requests
from entitysdk import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import (
    BrainLocation,
    BrainRegion,
    CellMorphology,
    CellMorphologyProtocol,
    MeasurementAnnotation,
    Subject,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from requests.exceptions import RequestException
from starlette.requests import Request

# --- Local project imports (used lazily inside functions) ---
from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_validation import process_and_convert_morphology


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
    """Load and cache the JSON template."""
    if hasattr(_get_template, "cached"):
        return _get_template.cached

    template_path = Path(__file__).parent / "morphology_template.json"
    template = json.loads(template_path.read_text())
    _get_template.cached = template
    return template


def _build_analysis_dict() -> dict:
    """Create the analysis dictionary on demand."""
    import app.endpoints.useful_functions.useful_functions as uf# noqa: PLC0415

    analysis_dict_base = uf.create_analysis_dict(_get_template())
    analysis_dict = dict(analysis_dict_base)

    if DEFAULT_NEURITE_DOMAIN in analysis_dict:
        default_analysis = analysis_dict[DEFAULT_NEURITE_DOMAIN]
        for domain in TARGET_NEURITE_DOMAINS:
            analysis_dict[domain] = default_analysis

    return analysis_dict


def _run_morphology_analysis(morphology_path: str) -> list[dict[str, Any]]:
    """Run NeuroM analysis and return filled measurement kinds."""
    import app.endpoints.useful_functions.useful_functions as uf# noqa: PLC0415

    try:
        neuron = nm.load_morphology(morphology_path)
        analysis_dict = _build_analysis_dict()
        results_dict = uf.build_results_dict(analysis_dict, neuron)
        filled = uf.fill_json(_get_template(), results_dict, entity_id="temp_id")
        return filled["data"][0]["measurement_kinds"]
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "MORPHOLOGY_ANALYSIS_ERROR",
                "detail": f"Error during morphology analysis: {e!s}",
            },
        ) from e


NEW_ENTITY_DEFAULTS = {
    "authorized_public": False,
    "license_id": None,
    "name": "test",
    "description": "string",
    "location": {"x": 0, "y": 0, "z": 0},
    "legacy_id": ["string"],
    "brain_region_id": "72893207-1e8f-48f3-b17b-075b58b9fac5",
    "subject_id": "9edb44c6-33b5-403b-8ab6-0890cfb12d07",
    "cell_morphology_protocol_id": None,
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


def _setup_context_and_client(
    user_context: UserContextDep, virtual_lab_id: str, project_id: str, request: Request
) -> Client:
    modified_context = user_context.model_copy(
        update={
            "virtual_lab_id": UUID(virtual_lab_id),
            "project_id": UUID(project_id),
        }
    )
    return get_client(user_context=modified_context, request=request)


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

    return morphology_name, file_extension, content, metadata_obj


T = TypeVar("T", bound=BaseEntity)


def register_morphology(client: Client, new_item: dict[str, Any]) -> Any:
    def _get_entity(key_suffix: str, entity_class: type[T]) -> T | None:
        entity_id_key = f"{key_suffix}_id"
        entity_id = new_item.get(entity_id_key)
        if entity_id is None:
            return None
        try:
            return client.search_entity(entity_type=entity_class, query={"id": entity_id}).one()
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

    subject = _get_entity("subject", Subject)
    brain_region = _get_entity("brain_region", BrainRegion)
    morphology_protocol = _get_entity("cell_morphology_protocol", CellMorphologyProtocol)

    name = new_item.get("name")
    description = new_item.get("description")

    morphology = CellMorphology(
        cell_morphology_protocol=morphology_protocol,
        name=name,
        description=description,
        subject=subject,
        brain_region=brain_region,
        location=brain_location,
        legacy_id=None,
        authorized_public=False,
    )

    registered = client.register_entity(entity=morphology)
    return registered


def register_assets(
    client: Client,
    entity_id: str,
    file_folder: str,
    morphology_name: str,
) -> dict[str, Any]:
    file_path_obj = pathlib.Path(file_folder) / morphology_name
    file_path = str(file_path_obj)

    if not file_path_obj.exists():
        error_msg = f"Asset file not found at path: {file_path}"
        raise FileNotFoundError(error_msg)

    file_extension = file_path_obj.suffix
    extension_map = {
        ".asc": "application/asc",
        ".swc": "application/swc",
        ".h5": "application/x-hdf5",
    }
    mime_type = extension_map.get(file_extension.lower())
    if not mime_type:
        error_msg = f"Unsupported file extension: '{file_extension}'."
        raise ValueError(error_msg)

    try:
        asset1 = client.upload_file(
            entity_id=entity_id,
            entity_type=CellMorphology,
            file_path=file_path,
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
        return asset1


def register_measurements(
    client: Client,
    entity_id: str,
    measurements: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        measurement_annotation = MeasurementAnnotation(
            entity_id=entity_id,
            entity_type="cell_morphology",
            measurement_kinds=measurements,
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
        return registered


def _prepare_entity_payload(
    metadata_obj: MorphologyMetadata, original_filename: str
) -> dict[str, Any]:
    entity_payload = NEW_ENTITY_DEFAULTS.copy()
    update_map = metadata_obj.model_dump(exclude_none=True)
    entity_payload.update(update_map)

    if entity_payload.get("name") in {"test", None}:
        entity_payload["name"] = f"Morphology: {original_filename}"

    return entity_payload


def _register_assets_and_measurements(
    client: Client,
    entity_id: str,
    morphology_name: str,
    content: bytes,
    measurement_list: list[dict[str, Any]],
    outputfile1: str,
    outputfile2: str,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir_for_upload:
        temp_upload_path_obj = pathlib.Path(temp_dir_for_upload) / morphology_name
        temp_upload_path_obj.write_bytes(content)
        register_assets(client, entity_id, temp_dir_for_upload, morphology_name)

    if outputfile1:
        output1_path_obj = pathlib.Path(outputfile1)
        if output1_path_obj.exists():
            register_assets(client, entity_id, str(output1_path_obj.parent), output1_path_obj.name)

    if outputfile2:
        output2_path_obj = pathlib.Path(outputfile2)
        if output2_path_obj.exists():
            register_assets(client, entity_id, str(output2_path_obj.parent), output2_path_obj.name)

    register_measurements(client, entity_id, measurement_list)


@router.post(
    "/morphology-metrics-entity-registration",
    summary="Calculate morphology metrics and register entities.",
    description=(
        "Performs analysis on a neuron file (.swc, .h5, or .asc) and registers the entity, "
        "asset, and measurements."
    ),
)
async def morphology_metrics_calculation(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    virtual_lab_id: Annotated[str, Form()],
    project_id: Annotated[str, Form()],
    user_context: UserContextDep,
    request: Request,
    metadata: Annotated[str, Form()] = "{}",
) -> dict:
    client = _setup_context_and_client(user_context, virtual_lab_id, project_id, request)

    (
        morphology_name,
        file_extension,
        content,
        metadata_obj,
    ) = await _parse_file_and_metadata(file, metadata)

    entity_id = "UNKNOWN"
    entity_payload = _prepare_entity_payload(metadata_obj, morphology_name)

    try:
        with ExitStack() as stack:
            temp_file_obj = stack.enter_context(
                tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
            )
            temp_file_path = temp_file_obj.name
            temp_file_obj.write(content)
            temp_file_obj.close()
            stack.callback(pathlib.Path(temp_file_path).unlink, missing_ok=True)

            outputfile1, outputfile2 = await process_and_convert_morphology(
                temp_file_path=temp_file_path, file_extension=file_extension
            )
            if outputfile1:
                stack.callback(pathlib.Path(outputfile1).unlink, missing_ok=True)
            if outputfile2:
                stack.callback(pathlib.Path(outputfile2).unlink, missing_ok=True)

            measurement_list = _run_morphology_analysis(temp_file_path)

            data = register_morphology(client, entity_payload)
            entity_id = str(data.id)

            _register_assets_and_measurements(
                client,
                entity_id,
                morphology_name,
                content,
                measurement_list,
                outputfile1,
                outputfile2,
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
    else:
        return {"entity_id": entity_id, "status": "success", "morphology_name": morphology_name}
