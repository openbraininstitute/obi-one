import pathlib
import tempfile
import zipfile
from http import HTTPStatus
from typing import Annotated, Literal

import aiofiles
import entitysdk.client
import entitysdk.exception
import morphio
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from morph_tool import convert

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.core.exception import ProtocolNotFoundError
from obi_one.scientific.circuit_metrics.circuit_metrics import (
    CircuitMetricsOutput,
    CircuitNodesetsResponse,
    CircuitPopulationsResponse,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.ephys_extraction.ephys_extraction import (
    CALCULATED_FEATURES,
    STIMULI_TYPES,
    AmplitudeInput,
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MORPHOLOGY_METRICS,
    MorphologyMetricsOutput,
    get_morphology_metrics,
)


def _handle_empty_file(file: UploadFile) -> None:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


def activate_morphology_endpoint(router: APIRouter) -> None:
    """Define neuron morphology metrics endpoint."""

    # ... (unchanged, same as in the original file)
    @router.get(
        "/neuron-morphology-metrics/{reconstruction_morphology_id}",
        summary="Neuron morphology metrics",
        description=(
            "This calculates neuron morphology metrics for a given reconstruction morphology."
        ),
    )
    def neuron_morphology_metrics_endpoint(
        reconstruction_morphology_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        requested_metrics: Annotated[
            list[Literal[*MORPHOLOGY_METRICS]] | None,  # type: ignore[misc]
            Query(
                description="List of requested metrics",
            ),
        ] = None,
    ) -> MorphologyMetricsOutput:
        L.info("get_morphology_metrics")
        try:
            metrics = get_morphology_metrics(
                reconstruction_morphology_id=reconstruction_morphology_id,
                db_client=db_client,
                requested_metrics=requested_metrics,
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": (
                        f"Reconstruction morphology {reconstruction_morphology_id} not found."
                    ),
                },
            ) from err

        if metrics:
            return metrics
        L.error(
            f"Reconstruction morphology {reconstruction_morphology_id} metrics computation issue"
        )
        raise ApiError(
            message="Asset not found",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )


def activate_ephys_endpoint(router: APIRouter) -> None:
    """Define electrophysiology recording metrics endpoint."""

    # ... (unchanged, same as in the original file)
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


def activate_test_endpoint(router: APIRouter) -> None:
    """Define neuron file test endpoint."""

    @router.post(
        "/test-neuron-file",
        summary="Upload and validate neuron file",
        description="Tests a neuron file (.swc, .h5, or .asc) with basic validation.",
    )
    async def test_neuron_file(
        file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    ) -> FileResponse:
        L.info(f"Received file upload: {file.filename}")
        allowed_extensions = {".swc", ".h5", ".asc"}
        file_extension = f".{file.filename.split('.')[-1].lower()}" if file.filename else ""

        if not file.filename or file_extension not in allowed_extensions:
            L.error(f"Invalid file extension: {file_extension}")
            valid_extensions = ", ".join(allowed_extensions)
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.BAD_REQUEST,
                    "detail": f"Invalid file extension. Must be one of {valid_extensions}",
                },
            )

        try:
            content = await file.read()
            if not content:
                _handle_empty_file(file)
        except ValueError as e:
            L.error(f"Error reading file {file.filename}: {e!s}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_SERVER_ERROR,
                    "detail": f"Error reading file: {e!s}",
                },
            ) from e

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            morphio.set_raise_warnings(False)
            m = morphio.Morphology(temp_file_path)
            # now convert the morphology
            outputfile1 = temp_file_path.replace(".swc", "_converted.h5")
            outputfile2 = temp_file_path.replace(".swc", "_converted.asc")

            convert(temp_file_path, outputfile1)
            convert(temp_file_path, outputfile2)

        except Exception as e:
            L.error(f"Morphio error loading file {file.filename}: {e!s}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_SERVER_ERROR,
                    "detail": f"NeuroM failure: {e!s}",
                },
            ) from e

        try:
            zip_filename = "morph_archive.zip"
            async with aiofiles.open(zip_filename, "wb") as f:
                with zipfile.ZipFile(f, "w") as my_zip:
                    my_zip.write(outputfile1, arcname=f"{pathlib.Path(outputfile1).stem}.h5")
                    my_zip.write(outputfile2, arcname=f"{pathlib.Path(outputfile2).stem}.asc")
        except Exception as e:
            L.error(f"Error creating zip file: {e!s}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_SERVER_ERROR,
                    "detail": f"Error creating zip file: {e!s}",
                },
            ) from e
        finally:
            if "temp_file_path" in locals():
                try:
                    pathlib.Path(temp_file_path).unlink()
                    pathlib.Path(outputfile1).unlink()
                    pathlib.Path(outputfile2).unlink()
                except OSError as e:
                    L.error(f"Error deleting temporary files: {e!s}")

        L.info(f"File {file.filename} passed basic validation")

        # Return the zip file as a FileResponse
        return FileResponse(path=zip_filename, filename=zip_filename, media_type="application/zip")


def activate_circuit_endpoints(router: APIRouter) -> None:
    """Define circuit-related endpoints."""

    # ... (unchanged, same as in the original file)
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


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_morphology_endpoint(router)
    activate_ephys_endpoint(router)
    activate_test_endpoint(router)
    activate_circuit_endpoints(router)
    return router
