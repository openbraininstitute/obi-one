import asyncio
import pathlib
import tempfile
import zipfile
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Literal

import aiofiles
import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.core.exception import ProtocolNotFoundError
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsOutput,
    CircuitNodesetsResponse,
    CircuitPopulationsResponse,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.library.entity_property_types import CircuitPropertyType
from obi_one.scientific.library.ephys_extraction import (
    CALCULATED_FEATURES,
    STIMULI_TYPES,
    AmplitudeInput,
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)
from obi_one.scientific.library.morphology_metrics import (
    MORPHOLOGY_METRICS,
    MorphologyMetricsOutput,
    get_morphology_metrics,
)

# ————————————————————————————————————————————————————————
# Constants
# ————————————————————————————————————————————————————————
MAX_UPLOAD_SIZE = 1_073_741_824  # 1 GB
CHUNK_SIZE = 1024 * 1024  # 1 MB


def _handle_empty_file(file: UploadFile) -> None:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.INVALID_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


# ————————————————————————————————————————————————————————
# Async Streaming Helper (Memory-Efficient, Non-Blocking)
# ————————————————————————————————————————————————————————
async def stream_upload_to_tempfile(file: UploadFile, suffix: str) -> str:
    """Stream UploadFile to disk in 1 MB chunks using async file.read().
    No full file in memory. Fully non-blocking.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name

    try:
        await file.seek(0)  # Reset pointer

        async with aiofiles.open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                await f.write(chunk)

    except Exception:
        if pathlib.Path(temp_path).exists():
            pathlib.Path(temp_path).unlink(missing_ok=True)
        raise
    else:
        return temp_path  # Now safely in `else` block
    finally:
        # Cleanup only if something went wrong and file wasn't returned
        pass  # Return happened in `else`, so no cleanup here


# ————————————————————————————————————————————————————————
# Morphology Metrics Endpoint
# ————————————————————————————————————————————————————————
def activate_morphology_endpoint(router: APIRouter) -> None:
    """Define neuron morphology metrics endpoint."""

    @router.get(
        "/neuron-morphology-metrics/{cell_morphology_id}",
        summary="Neuron morphology metrics",
        description="This calculates neuron morphology metrics for a given cell morphology.",
    )
    def neuron_morphology_metrics_endpoint(
        cell_morphology_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        requested_metrics: Annotated[
            list[Literal[*MORPHOLOGY_METRICS]] | None,
            Query(description="List of requested metrics"),
        ] = None,
    ) -> MorphologyMetricsOutput:
        L.info("get_morphology_metrics")
        try:
            metrics = get_morphology_metrics(
                cell_morphology_id=cell_morphology_id,
                db_client=db_client,
                requested_metrics=requested_metrics,
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Cell morphology {cell_morphology_id} not found.",
                },
            ) from err

        if metrics:
            return metrics
        L.error(f"Cell morphology {cell_morphology_id} metrics computation issue")
        raise ApiError(
            message="Asset not found",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )


# ————————————————————————————————————————————————————————
# Electrophysiology Endpoint
# ————————————————————————————————————————————————————————
def activate_ephys_endpoint(router: APIRouter) -> None:
    """Define electrophysiology recording metrics endpoint."""

    @router.get(
        "/electrophysiologyrecording-metrics/{trace_id}",
        summary="Electrophysiology recording metrics",
        description="This calculates electrophysiology traces metrics for a particular recording",
    )
    def electrophysiologyrecording_metrics_endpoint(
        trace_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        requested_metrics: Annotated[CALCULATED_FEATURES | None, Query()] = None,
        amplitude: Annotated[AmplitudeInput, Depends()] = None,
        protocols: Annotated[STIMULI_TYPES | None, Query()] = None,
    ) -> ElectrophysiologyMetricsOutput:
        try:
            ephys_metrics = get_electrophysiology_metrics(
                trace_id=trace_id,
                entity_client=db_client,
                calculated_feature=requested_metrics,
                amplitude=amplitude,
                stimuli_types=protocols,
            )
        except ProtocolNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e!s}") from e
        return ephys_metrics


# ————————————————————————————————————————————————————————
# Morphology File Processing Helpers
# ————————————————————————————————————————————————————————
async def _process_and_convert_morphology(
    file: UploadFile, temp_file_path: str, file_extension: str
) -> tuple[str, str]:
    """Process and convert a neuron morphology file."""
    import morphio  # noqa: PLC0415
    from morph_tool import convert  # noqa: PLC0415

    try:
        morphio.set_raise_warnings(False)
        _ = morphio.Morphology(temp_file_path)

        base = Path(temp_file_path).with_suffix("")
        if file_extension == ".swc":
            outputfile1 = f"{base}_converted.h5"
            outputfile2 = f"{base}_converted.asc"
        elif file_extension == ".h5":
            outputfile1 = f"{base}_converted.swc"
            outputfile2 = f"{base}_converted.asc"
        else:  # .asc
            outputfile1 = f"{base}_converted.swc"
            outputfile2 = f"{base}_converted.h5"

        convert(temp_file_path, outputfile1)
        convert(temp_file_path, outputfile2)

    except Exception as e:
        L.error(f"Morphio error loading file {file.filename}: {e!s}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Failed to load and convert the file: {e!s}",
            },
        ) from e
    else:
        return outputfile1, outputfile2


def _create_zip_file_sync(zip_path: str, file1: str, file2: str) -> None:
    """Synchronously create a zip file from two files."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as my_zip:
        my_zip.write(file1, arcname=Path(file1).name)
        my_zip.write(file2, arcname=Path(file2).name)


async def _create_and_return_zip(outputfile1: str, outputfile2: str) -> FileResponse:
    """Asynchronously creates a zip file and returns it as a FileResponse."""
    zip_filename = "morph_archive.zip"
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            _create_zip_file_sync,
            zip_filename,
            outputfile1,
            outputfile2,
        )
    except Exception as e:
        L.error(f"Error creating zip file: {e!s}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Error creating zip file: {e!s}",
            },
        ) from e
    else:
        L.info(f"Created zip file: {zip_filename}")
        return FileResponse(path=zip_filename, filename=zip_filename, media_type="application/zip")


# ————————————————————————————————————————————————————————
# Test Neuron File Endpoint (STREAMED)
# ————————————————————————————————————————————————————————
def activate_test_endpoint(router: APIRouter) -> None:
    """Define neuron file test endpoint."""

    @router.post(
        "/test-neuron-file",
        summary="Validate morphology format and returns the conversion to other formats.",
        description="Tests a neuron file (.swc, .h5, or .asc) with basic validation.",
        response_class=FileResponse,
    )
    async def test_neuron_file(
        request: Request,
        file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    ) -> FileResponse:
        # Enforce max size
        if int(request.headers.get("content-length", 0)) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large (>1GB)")

        file_extension = Path(file.filename).suffix.lower() if file.filename else ""
        allowed = {".swc", ".h5", ".asc"}
        if file_extension not in allowed:
            raise HTTPException(
                status_code=400, detail=f"Invalid extension. Must be one of {', '.join(allowed)}"
            )

        temp_file_path = outputfile1 = outputfile2 = ""

        try:
            temp_file_path = await stream_upload_to_tempfile(file, suffix=file_extension)

            if Path(temp_file_path).stat().st_size == 0:
                _handle_empty_file(file)

            outputfile1, outputfile2 = await _process_and_convert_morphology(
                file=file, temp_file_path=temp_file_path, file_extension=file_extension
            )

            return await _create_and_return_zip(outputfile1, outputfile2)

        finally:
            for path in [temp_file_path, outputfile1, outputfile2]:
                if path and Path(path).exists():
                    try:
                        Path(path).unlink()
                    except OSError as e:
                        L.warning(f"Failed to delete temp file {path}: {e}")


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


# ————————————————————————————————————————————————————————
# Validate NWB File Endpoint (STREAMED + SIZE LIMIT)
# ————————————————————————————————————————————————————————
def activate_validate_nwb_endpoint(router: APIRouter) -> None:
    """Define NWB file validation endpoint."""

    @router.post(
        "/validate-nwb-file",
        summary="Validate NWB file format.",
        description="Validates an uploaded .nwb file using registered readers.",
    )
    async def validate_nwb_file(
        request: Request,
        file: Annotated[UploadFile, File(description="NWB file to upload (.nwb)")],
    ) -> NWBValidationResponse:
        # Enforce max size
        if int(request.headers.get("content-length", 0)) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail={"code": ApiErrorCode.INVALID_REQUEST, "detail": "File too large (>1GB)"},
            )

        file_extension = Path(file.filename).suffix.lower() if file.filename else ""
        if file_extension != ".nwb":
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": "Invalid file extension. Must be .nwb",
                },
            )

        temp_file_path = ""

        try:
            temp_file_path = await stream_upload_to_tempfile(file, suffix=".nwb")

            if Path(temp_file_path).stat().st_size == 0:
                _handle_empty_file(file)

            validate_all_nwb_readers(temp_file_path)

            return NWBValidationResponse(
                status="success",
                message="NWB file validation successful.",
            )

        except RuntimeError as e:
            L.error(f"NWB validation failed: {e!s}")
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": f"NWB validation failed: {e!s}",
                },
            ) from e
        except OSError as e:
            L.error(f"File system error during NWB validation: {e!s}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"code": "INTERNAL_ERROR", "detail": f"Internal Server Error: {e!s}"},
            ) from e
        finally:
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                except OSError as e:
                    L.warning(f"Failed to delete temp NWB file: {e}")


# ————————————————————————————————————————————————————————
# Circuit Endpoints
# ————————————————————————————————————————————————————————
def activate_circuit_endpoints(router: APIRouter) -> None:
    """Define circuit-related endpoints."""

    @router.get(
        "/circuit-metrics/{circuit_id}",
        summary="Circuit metrics",
        description="This calculates circuit metrics",
    )
    def circuit_metrics_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        level_of_detail_nodes: Annotated[
            CircuitStatsLevelOfDetail,
            Query(description="Level of detail for node populations analysis"),
        ] = CircuitStatsLevelOfDetail.none,
        level_of_detail_edges: Annotated[
            CircuitStatsLevelOfDetail,
            Query(description="Level of detail for edge populations analysis"),
        ] = CircuitStatsLevelOfDetail.none,
    ) -> CircuitMetricsOutput:
        try:
            level_of_detail_nodes_dict = {"_ALL_": level_of_detail_nodes}
            level_of_detail_edges_dict = {"_ALL_": level_of_detail_edges}
            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes=level_of_detail_nodes_dict,
                level_of_detail_edges=level_of_detail_edges_dict,
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err
        return circuit_metrics

    @router.get(
        "/circuit/{circuit_id}/biophysical_populations",
        summary="Circuit populations",
        description="This returns the list of biophysical node populations for a given circuit.",
    )
    def circuit_populations_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ) -> CircuitPopulationsResponse:
        try:
            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
                level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err
        return CircuitPopulationsResponse(
            populations=circuit_metrics.names_of_biophys_node_populations
        )

    @router.get(
        "/circuit/{circuit_id}/nodesets",
        summary="Circuit nodesets",
        description="This returns the list of nodesets for a given circuit.",
    )
    def circuit_nodesets_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ) -> CircuitNodesetsResponse:
        try:
            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
                level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err
        return CircuitNodesetsResponse(nodesets=circuit_metrics.names_of_nodesets)

    @router.get(
        "/mapped-circuit-properties/{circuit_id}",
        summary="Mapped circuit properties",
        description="Returns a dictionary of mapped circuit properties.",
    )
    def mapped_circuit_properties_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ) -> dict:
        try:
            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
                level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err
        else:  # TRY300
            return {CircuitPropertyType.NODE_SET: circuit_metrics.names_of_nodesets}


# ————————————————————————————————————————————————————————
# Activate All Endpoints
# ————————————————————————————————————————————————————————
def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_morphology_endpoint(router)
    activate_ephys_endpoint(router)
    activate_test_endpoint(router)
    activate_validate_nwb_endpoint(router)
    activate_circuit_endpoints(router)
    return router
