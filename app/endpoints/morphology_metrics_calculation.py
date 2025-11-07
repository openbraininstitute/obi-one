import json
import tempfile
import traceback
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Final

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
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from requests.exceptions import RequestException
from starlette.requests import Request

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
def _run_morphology_analysis(file_path: Path) -> dict[str, Any]:
    """
    Run morphological metrics extraction using neurom.
    Lazily imports neurom to avoid MPI/NEURON dependency issues in test environments.
    """
    try:
        import neurom as nm  # noqa: PLC0415 - intentional lazy import
    except ImportError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Neurom library not available: {err}",
        ) from err

    try:
        morph = nm.load_morphology(file_path)
        results = {
            "neurite_length": nm.get("total_length", morph),
            "neurite_number": len(morph.neurites),
            "neurite_types": [n.type for n in morph.neurites],
        }
    except Exception as err:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Error during morphology analysis: {err}",
        ) from err

    return results


# --------------------------------------------------------------------------
# FastAPI Router and Endpoint
# --------------------------------------------------------------------------
router = APIRouter()


@router.post("/declared/morphology-metrics-entity-registration")
async def register_morphology_metrics(
    file: Annotated[UploadFile, File(...)],
    _client: Annotated[Client, Depends(get_client)],
    _user_ctx: Annotated[UserContextDep, Depends(user_verified)],
) -> dict[str, Any]:
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
        metrics = _run_morphology_analysis(tmp_path)

    # Example response payload
    return {
        "file_name": file.filename,
        "metrics": metrics,
        "status": "success",
    }
