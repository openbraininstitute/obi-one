import pathlib
import tempfile
from http import HTTPStatus
from typing import Annotated, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.errors import ApiErrorCode
from app.logger import L

# --------------------------------------------

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

# Max file size: 150 MB
MAX_FILE_SIZE = 150 * 1024 * 1024


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the maximum allowed size."""


# --- NWB Validation Protocols and Reader Function ---

TEST_PROTOCOLS = [
    "APThreshold",
    "SAPThres1",
    "SAPThres2",
    "SAPThres3",
    "SAPTres1",
    "SAPTres2",
    "SAPTres3",
    "Step_150",
    "Step_200",
    "Step_250",
    "Step_150_hyp",
    "Step_200_hyp",
    "Step_250_hyp",
    "C1HP1sec",
    "C1_HP_1sec",
    "IRrest",
    "SDelta",
    "SIDRest",
    "SIDThres",
    "SIDTres",
    "SRac",
    "pulser",
    "A",
    "maria-STEP",
    "APDrop",
    "APResh",
    "C1_HP_0.5sec",
    "C1step_1sec",
    "C1step_ag",
    "C1step_highres",
    "HighResThResp",
    "IDRestTest",
    "LoOffset1",
    "LoOffset3",
    "Rin",
    "STesteCode",
    "SSponAPs",
    "SponAPs",
    "SpontAPs",
    "Test_eCode",
    "TesteCode",
    "step_1",
    "step_2",
    "step_3",
    "IV_Test",
    "SIV",
    "APWaveform",
    "SAPWaveform",
    "Delta",
    "FirePattern",
    "H10S8",
    "H20S8",
    "H40S8",
    "IDRest",
    "IDThres",
    "IDThresh",
    "IDrest",
    "IDthresh",
    "IV",
    "IV2",
    "IV_-120",
    "IV_-120_hyp",
    "IV_-140",
    "Rac",
    "RMP",
    "SetAmpl",
    "SetISI",
    "SetISITest",
    "TestAmpl",
    "TestRheo",
    "TestSpikeRec",
    "SpikeRec",
    "ADHPdepol",
    "ADHPhyperpol",
    "ADHPrest",
    "SSpikeRec",
    "SpikeRec_Ih",
    "SpikeRec_Kv1.1",
    "scope",
    "spuls",
    "RPip",
    "RSealClose",
    "RSealOpen",
    "CalOU01",
    "CalOU04",
    "ElecCal",
    "NoiseOU3",
    "NoisePP",
    "SNoisePP",
    "SNoiseSpiking",
    "OU10Hi01",
    "OU10Lo01",
    "OU10Me01",
    "SResetITC",
    "STrueNoise",
    "SubWhiteNoise",
    "Truenoise",
    "WhiteNoise",
    "ResetITC",
    "SponHold25",
    "SponHold3",
    "SponHold30",
    "SSponHold",
    "SponNoHold20",
    "SponNoHold30",
    "SSponNoHold",
    "Spontaneous",
    "hold_dep",
    "hold_hyp",
    "StartHold",
    "StartNoHold",
    "StartStandeCode",
    "VacuumPulses",
    "sAHP",
    "IRdepol",
    "IRhyperpol",
    "IDdepol",
    "IDhyperpol",
    "SsAHP",
    "HyperDePol",
    "DeHyperPol",
    "NegCheops",
    "NegCheops1",
    "NegCheops2",
    "NegCheops3",
    "NegCheops4",
    "NegCheops5",
    "PosCheops",
    "Rin_dep",
    "Rin_hyp",
    "SineSpec",
    "SSineSpec",
    "Pulse",
    "S2",
    "s2",
    "S30",
    "SIne20Hz",
    "A___.ibw",
]


def validate_all_nwb_readers(nwb_file_path: str) -> None:
    """Try all NWB readers. Succeed if at least one works."""
    from bluepyefe.reader import (  # noqa: PLC0415
        AIBSNWBReader,
        BBPNWBReader,
        ScalaNWBReader,
        TRTNWBReader,
    )

    readers = [AIBSNWBReader, BBPNWBReader, ScalaNWBReader, TRTNWBReader]

    all_failed = "All NWB readers failed."

    for readerclass in readers:
        try:
            reader = readerclass(nwb_file_path, TEST_PROTOCOLS)
            data = reader.read()
            if data is not None:
                return
        except Exception as e:  # noqa: BLE001
            L.warning(
                "Reader %s failed for file %s: %s",
                readerclass.__name__,
                nwb_file_path,
                str(e),
            )
            continue
    raise RuntimeError(all_failed)


class NWBValidationResponse(BaseModel):
    """Schema for the NWB file validation success response."""

    status: str
    message: str


# -------------------------------------------------------------------------------------------------


def _handle_empty_file(file: UploadFile) -> NoReturn:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


# New helper function to abstract the raise statement (TRY301 fix)
def _handle_file_too_large(temp_path: str) -> NoReturn:
    """Handles cleanup and raises FileTooLargeError when the file size limit is exceeded."""
    pathlib.Path(temp_path).unlink(missing_ok=True)
    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    msg = f"File size exceeds the limit of {max_mb:.0f} MB"
    raise FileTooLargeError(msg)


def _save_upload_to_tempfile(file: UploadFile, suffix: str) -> str:
    """Save UploadFile to a temporary file synchronously."""
    chunk_size = 1024 * 1024  # 1 MB
    total_size = 0  # Track total size written

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name

        try:
            file.file.seek(0)  # Reset pointer
            while True:
                # Use chunk_size
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break

                chunk_len = len(chunk)
                total_size += chunk_len

                # Check size limit before writing
                if total_size > MAX_FILE_SIZE:
                    _handle_file_too_large(temp_path)

                temp_file.write(chunk)
        except Exception:
            if pathlib.Path(temp_path).exists():
                pathlib.Path(temp_path).unlink(missing_ok=True)
            raise
        else:
            return temp_path


def _cleanup_temp_file(temp_path: str) -> None:
    """Background task to clean up temporary file."""
    if temp_path and pathlib.Path(temp_path).exists():
        try:
            pathlib.Path(temp_path).unlink()
            L.debug(f"Cleaned up temp file: {temp_path}")
        except OSError as e:
            L.warning(f"Failed to delete temp NWB file: {e}")


# Endpoint logic is now a standalone function
def validate_nwb_file(
    file: Annotated[UploadFile, File(description="NWB file to upload (.nwb)")],
    background_tasks: BackgroundTasks,
) -> NWBValidationResponse:
    """Validates an uploaded .nwb file using registered readers."""
    file_extension = pathlib.Path(file.filename).suffix.lower() if file.filename else ""
    if file_extension != ".nwb":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": "Invalid file extension. Must be .nwb",
            },
        )

    temp_file_path = ""

    try:
        # Save upload synchronously (still non-blocking for other requests)
        temp_file_path = _save_upload_to_tempfile(file, suffix=".nwb")

        if pathlib.Path(temp_file_path).stat().st_size == 0:
            _handle_empty_file(file)

        # Validate the file synchronously
        validate_all_nwb_readers(temp_file_path)

        # Schedule cleanup as a background task
        background_tasks.add_task(_cleanup_temp_file, temp_file_path)

        return NWBValidationResponse(
            status="success",
            message="NWB file validation successful.",
        )

    except FileTooLargeError:
        L.error("NWB upload failed: File too large (Max: 50MB)")
        # Cleanup is handled inside _save_upload_to_tempfile
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": "Uploaded file is too large. Max size: 50 MB.",
            },
        ) from None

    except RuntimeError as e:
        L.error(f"NWB validation failed: {e!s}")
        # Clean up immediately on error
        if temp_file_path and pathlib.Path(temp_file_path).exists():
            try:
                pathlib.Path(temp_file_path).unlink()
            except OSError as cleanup_error:
                L.warning(f"Failed to delete temp NWB file: {cleanup_error}")

        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"NWB validation failed: {e!s}",
            },
        ) from e
    except OSError as e:
        L.error(f"File system error during NWB validation: {e!s}")
        # Clean up immediately on error
        if temp_file_path and pathlib.Path(temp_file_path).exists():
            try:
                pathlib.Path(temp_file_path).unlink()
            except OSError as cleanup_error:
                L.warning(f"Failed to delete temp NWB file: {cleanup_error}")

        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "detail": f"Internal Server Error: {e!s}"},
        ) from e


def activate_test_nwb_endpoint(router: APIRouter) -> None:
    """Define NWB file validation endpoint."""
    router.post(
        "/validate-nwb-file",
        summary="Validate NWB file format.",
        description="Validates an uploaded .nwb file using registered readers.",
    )(validate_nwb_file)


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_test_nwb_endpoint(router)
    return router


router = activate_declared_endpoints(router)
