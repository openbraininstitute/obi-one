import json
import pathlib
import tempfile
import traceback
from contextlib import suppress
from http import HTTPStatus
from typing import Annotated, Any, Final

import morphio
import neurom as nm
import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import OAuth2PasswordBearer
from morph_tool import convert
from pydantic import BaseModel

import app.endpoints.useful_functions.useful_functions as uf
from app.dependencies.auth import user_verified


class ApiErrorCode:
    BAD_REQUEST = "BAD_REQUEST"


ALLOWED_EXTENSIONS: Final[set[str]] = {".swc", ".h5", ".asc"}
ALLOWED_EXT_STR: Final[str] = ", ".join(ALLOWED_EXTENSIONS)

DEFAULT_NEURITE_DOMAIN: Final[str] = "basal_dendrite"
TARGET_NEURITE_DOMAINS: Final[list[str]] = ["apical_dendrite", "axon"]

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

# --- TOKEN ACCESS DEPENDENCY ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


def get_auth_token(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency that returns the raw token string from the Authorization header."""
    return token


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


async def _process_and_convert_morphology(
    # ARG001: Removed 'file' argument as it was unused.
    temp_file_path: str, file_extension: str
) -> tuple[str, str]:
    """Process and convert a neuron morphology file."""
    try:
        morphio.set_raise_warnings(False)
        _ = morphio.Morphology(temp_file_path)

        # Removed 'file' parameter from _process_and_convert_morphology call within this block.

        outputfile1, outputfile2 = "", ""
        if file_extension == ".swc":
            outputfile1 = temp_file_path.replace(".swc", "_converted.h5")
            outputfile2 = temp_file_path.replace(".swc", "_converted.asc")
        elif file_extension == ".h5":
            outputfile1 = temp_file_path.replace(".h5", "_converted.swc")
            outputfile2 = temp_file_path.replace(".h5", "_converted.asc")
        else:  # .asc
            outputfile1 = temp_file_path.replace(".asc", "_converted.swc")
            outputfile2 = temp_file_path.replace(".asc", "_converted.h5")

        convert(temp_file_path, outputfile1)
        convert(temp_file_path, outputfile2)

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Failed to load and convert the file: {e!s}",
            },
        ) from e
    else:
        return outputfile1, outputfile2


# the template is included with the code
TEMPLATE = {
    "data": [
        {
            "id": "00a0c678-1bce-40fa-a28a-2bc44ff36f43",
            "creation_date": "2024-07-24T12:43:55.989031Z",
            "update_date": "2024-07-24T12:43:56.054059Z",
            "entity_id": "e892fa95-c724-457a-8dc6-176f5d6cc5d9",
            "entity_type": "reconstruction_morphology",
            "measurement_kinds": [
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "μm", "value": 0.0}],
                    "pref_label": "neurite_max_radial_distance",
                },
                {
                    "structural_domain": "soma",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 9.845637133329614}
                    ],
                    "pref_label": "soma_radius",
                },
            ],
        }
    ],
    "pagination": {"page": 1, "page_size": 100, "total_items": 1},
    "facets": None,
}

_analysis_dict_base = uf.create_analysis_dict(TEMPLATE)
analysis_dict = dict(_analysis_dict_base)

if DEFAULT_NEURITE_DOMAIN in analysis_dict:
    default_analysis = analysis_dict[DEFAULT_NEURITE_DOMAIN]
    for domain in TARGET_NEURITE_DOMAINS:
        analysis_dict[domain] = default_analysis


def _run_morphology_analysis(morphology_path: str) -> list[dict[str, Any]]:
    try:
        neuron = nm.load_morphology(morphology_path)

        results_dict = uf.build_results_dict(analysis_dict, neuron)

        filled = uf.fill_json(TEMPLATE, results_dict, entity_id="temp_id")

        return filled["data"][0]["measurement_kinds"]

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "MORPHOLOGY_ANALYSIS_ERROR",
                "detail": f"Error during morphology analysis: {e!s}",
            },
        ) from e


# --- CONFIGURATION ---

# Global Constants for API (defaults)
VIRTUAL_LAB_ID = "bf7d398c-b812-408a-a2ee-098f633f7798"
PROJECT_ID = "100a9a8a-5229-4f3d-aef3-6a4184c59e74"

# Entity Registration Data (Defaults)
AGENT_ID = "4307c68c-4254-44a1-974f-1eedf5b0f16c"
ROLE_ID = "78b53cbf-ad29-49fd-82e7-d0bc328fc581"
MTYPE_CLASS_ID = "0791edc9-7ad4-4a94-a4a5-feab9b690d7e"

NEW_ENTITY_DEFAULTS = {
    "authorized_public": False,
    "license_id": None,
    "name": "test",
    "description": "string",
    "location": {"x": 0, "y": 0, "z": 0},
    "legacy_id": ["string"],
    "species_id": "b7ad4cca-4ac2-4095-9781-37fb68fe9ca1",
    "strain_id": None,
    "brain_region_id": "72893207-1e8f-48f3-b17b-075b58b9fac5",
    "subject_id": "9edb44c6-33b5-403b-8ab6-0890cfb12d07",
    "cell_morphology_protocol_id": None,
}


# --- Pydantic Model for Metadata (Used in the request Body) ---
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


# --- API CALL FUNCTIONS ---


def _api_post(url_path: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    # ANN202: Added return type annotation -> dict[str, Any]
    url = f"https://staging.openbraininstitute.org/api/entitycore/{url_path}"
    try:
        # S113: Added timeout
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "CONNECTION_ERROR", "detail": f"Connection Error: {e}"},
        ) from e


def register_morphology(
    token: str, new_item: dict[str, Any], virtual_lab_id: str, project_id: str
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": virtual_lab_id,
        "project-id": project_id,
    }
    return _api_post("cell-morphology", headers, new_item)


def register_assets(
    token: str,
    entity_id: str,
    file_folder: str,
    morphology_name: str,
    virtual_lab_id: str,
    project_id: str,
) -> dict[str, Any]:
    url = (
        f"https://staging.openbraininstitute.org/api/entitycore/cell-morphology/{entity_id}/assets"
    )

    # PTH118: Replaced os.path.join() with pathlib.Path
    file_path_obj = pathlib.Path(file_folder) / morphology_name
    file_path = str(file_path_obj)

    if not file_path_obj.exists():
        # TRY003, EM102: Assigned f-string to a variable before raising
        error_msg = f"Asset file not found at path: {file_path}"
        raise FileNotFoundError(error_msg)

    # PTH122: Replaced os.path.splitext() with pathlib.Path.suffix
    file_extension = file_path_obj.suffix
    extension_map = {
        ".asc": "application/asc",
        ".swc": "application/swc",
        ".h5": "application/x-hdf5",
    }
    mime_type = extension_map.get(file_extension.lower())
    if not mime_type:
        # TRY003, EM102: Assigned f-string to a variable before raising
        error_msg = f"Unsupported file extension: '{file_extension}'."
        raise ValueError(error_msg)

    headers = {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": virtual_lab_id,
        "project-id": project_id,
    }
    data = {"label": "morphology", "meta": {}}
    try:
        # PTH123: Replaced open() with Path.open()
        with file_path_obj.open("rb") as f:
            files = {"file": (morphology_name, f, mime_type)}
            # S113: Added timeout
            response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            response.raise_for_status()
            return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "CONNECTION_ERROR", "detail": f"Connection Error: {e}"},
        ) from e


def register_measurements(
    token: str,
    entity_id: str,
    measurements: list[dict[str, Any]],
    virtual_lab_id: str,
    project_id: str,
) -> dict[str, Any]:
    # N806: Converted API_ENDPOINT to lowercase `api_endpoint`
    api_endpoint = "https://staging.openbraininstitute.org/api/entitycore/measurement-annotation"
    headers = {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": virtual_lab_id,
        "project-id": project_id,
    }
    payload = {
        "entity_id": entity_id,
        "name": f"Morphometrics for {entity_id}",
        "description": "Automated morphology metrics calculation.",
        "entity_type": "cell_morphology",
        "measurement_kinds": measurements,
    }
    try:
        # S113: Added timeout
        response = requests.post(api_endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "CONNECTION_ERROR", "detail": f"Connection Error: {e}"},
        ) from e


# --- NEW HELPER FUNCTION TO REDUCE LOCAL VARIABLES IN MAIN ENDPOINT ---
def _prepare_entity_payload(
    metadata_obj: MorphologyMetadata, original_filename: str
) -> dict[str, Any]:
    """Prepares the entity payload for registration, reducing complexity in the main function."""
    entity_payload = NEW_ENTITY_DEFAULTS.copy()
    update_map = metadata_obj.model_dump(exclude_none=True)
    entity_payload.update(update_map)

    # PLR6201: Converted tuple to set for membership test
    if entity_payload.get("name") in {NEW_ENTITY_DEFAULTS["name"], None}:
        entity_payload["name"] = f"Morphology: {original_filename}"

    return entity_payload

# --- MAIN ENDPOINT ---


@router.post(
    "/morphology-metrics-entity-registration",
    summary="Calculate morphology metrics and register entities.",
    # E501: Broke up long line (description)
    description=(
        "Performs analysis on a neuron file (.swc, .h5, or .asc) and registers the entity, "
        "asset, and measurements."
    ),
)
async def morphology_metrics_calculation(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    token: Annotated[str, Depends(get_auth_token)],
    virtual_lab_id: Annotated[str, Form()] = VIRTUAL_LAB_ID,
    project_id: Annotated[str, Form()] = PROJECT_ID,
    metadata: Annotated[str, Form()] = "{}",
    # PLR0914: The number of local variables is now 15 (max allowed) or less
) -> dict:
    morphology_name = file.filename
    file_extension = _validate_file_extension(morphology_name)
    content = await file.read()

    if not content:
        _handle_empty_file(file)

    # Parse metadata JSON string
    try:
        metadata_dict = json.loads(metadata) if metadata != "{}" else {}
        metadata_obj = MorphologyMetadata(**metadata_dict)
    except (json.JSONDecodeError, ValueError) as e:
        # B904: Added 'from e' to re-raise exception
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={"code": "INVALID_METADATA", "detail": f"Invalid metadata: {e}"},
        ) from e

    temp_file_path = ""
    entity_id = "UNKNOWN"

    outputfile1, outputfile2 = "", ""
    try:
        # --- 1. ANALYSIS ---

        # 1a. Write the uploaded content to a temporary file for neurom analysis
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Conversion
        # ARG001: Removed unused 'file' argument
        outputfile1, outputfile2 = await _process_and_convert_morphology(
            temp_file_path=temp_file_path, file_extension=file_extension
        )

        # 1b. Run morphology analysis
        measurement_list = _run_morphology_analysis(temp_file_path)

        # --- 2. API REGISTRATION ---

        # 2a/b. Entity Registration
        # Refactored logic into a helper function to reduce local variable count
        entity_payload = _prepare_entity_payload(metadata_obj, morphology_name)

        data = register_morphology(token, entity_payload, virtual_lab_id, project_id)
        entity_id = data.get("id", "ID_NOT_FOUND")

        # 2c. Register Asset (Original uploaded file)
        with tempfile.TemporaryDirectory() as temp_dir_for_upload:
            # PTH118, ASYNC230, PTH123, FURB103: Replaced os.path.join and blocking file open/write
            # with Path object and write_bytes for async-safe operation.
            temp_upload_path_obj = pathlib.Path(temp_dir_for_upload) / morphology_name
            temp_upload_path_obj.write_bytes(content)

            register_assets(
                token,
                entity_id,
                temp_dir_for_upload,
                morphology_name,
                virtual_lab_id,
                project_id,
            )

        # Register Asset (Converted File 1)
        output1_path_obj = pathlib.Path(outputfile1)
        register_assets(
            token,
            entity_id,
            file_folder=str(output1_path_obj.parent),
            morphology_name=output1_path_obj.name,
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
        )

        # Register Asset (Converted File 2)
        output2_path_obj = pathlib.Path(outputfile2)
        register_assets(
            token,
            entity_id,
            file_folder=str(output2_path_obj.parent),
            morphology_name=output2_path_obj.name,
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
        )

        # 2d. Register Measurements
        register_measurements(token, entity_id, measurement_list, virtual_lab_id, project_id)

        # TRY300: Moved return statement outside of try block into an else block
    except HTTPException:
        # Re-raise explicit HTTP exceptions for FastAPI to handle
        raise
    except Exception as e:
        # PLC0415: import traceback moved to top-level
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
    finally:
        # 3. CLEANUP
        if temp_file_path:
            with suppress(OSError):
                pathlib.Path(temp_file_path).unlink(missing_ok=True)
                pathlib.Path(outputfile1).unlink(missing_ok=True)
                pathlib.Path(outputfile2).unlink(missing_ok=True)