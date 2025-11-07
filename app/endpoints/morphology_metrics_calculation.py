import json
import pathlib
import tempfile
import traceback
from contextlib import ExitStack, suppress
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Final, TypeVar
from uuid import UUID

# --- Removed top-level neurom import ---
# import neurom as nm

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
TARGET_NEURITE_DOMAINS: Final[list[str]] = [
    "axon",
    "basal_dendrite",
    "apical_dendrite",
    "soma",
]


# --------------------------------------------------------------------------
# Function that performs neurom-based analysis
# --------------------------------------------------------------------------
def _run_morphology_analysis(file_path: Path, output_dir: Path) -> dict[str, Any]:
    """
    Run morphological metrics extraction using neurom.
    Lazily imports neurom to avoid MPI/NEURON dependency issues in test environments.
    """
    try:
        import neurom as nm  # Lazy import to prevent load errors in test/CI environments
    except ImportError as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Neurom library not available: {e}",
        )

    try:
        morph = nm.load_morphology(file_path)
        results = {
            "neurite_length": nm.get("total_length", morph),
            "neurite_number": len(morph.neurites),
            "neurite_types": [n.type for n in morph.neurites],
        }
        return results
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Error during morphology analysis: {str(e)}",
        )


# --------------------------------------------------------------------------
# Example endpoint definition (preserved)
# --------------------------------------------------------------------------
router = APIRouter()


@router.post("/declared/morphology-metrics-entity-registration")
async def register_morphology_metrics(
    request: Request,
    file: UploadFile = File(...),
    client: Client = Depends(get_client),
    user_ctx: UserContextDep = Depends(user_verified),
):
    """Endpoint for registering morphology metrics."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Unsupported file format: {suffix}. Must be one of {ALLOWED_EXT_STR}.",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / file.filename
        tmp_path.write_bytes(await file.read())

        # Run neurom analysis (lazy import inside)
        metrics = _run_morphology_analysis(tmp_path, Path(tmpdir))

        # Example response payload
        return {
            "file_name": file.filename,
            "metrics": metrics,
            "status": "success",
        }
