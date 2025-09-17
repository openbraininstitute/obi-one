import tempfile
from http import HTTPStatus
from io import BytesIO
from typing import Annotated, Literal

import entitysdk.client
import entitysdk.exception
import neurom as nm
from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
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


def activate_declared_endpoints(router: APIRouter) -> APIRouter:  # noqa: C901
    @router.get(
        "/neuron-morphology-metrics/{reconstruction_morphology_id}",
        summary="Neuron morphology metrics",
        description="This calculates neuron morphology metrics for a given reconstruction \
                    morphology.",
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
        """Calculates neuron morphology metrics for a given reconstruction morphology.

        - **reconstruction_morphology_id**: ID of the reconstruction morphology.
        - **requested_metrics**: List of requested metrics (optional).
        """
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

    @router.get(
        "/electrophysiologyrecording-metrics/{trace_id}",
        summary="electrophysiology recording metrics",
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
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Internal Server Error: {e}"
            ) from e
        else:
            return ephys_metrics

    @router.post(
        "/upload-neuron-file",
        summary="Upload and validate neuron file",
        description="Uploads a neuron file (.swc, .h5, or .asc) and performs basic validation.",
    )
    async def upload_neuron_file(
        file: Annotated[
            UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")
        ],
    ) -> JSONResponse:
        """Uploads and validates a neuron file.

        - **file**: The neuron file to upload (must be .swc, .h5, or .asc).
        Returns a JSON response with validation status (pass/fail).
        """
        L.info(f"Received file upload: {file.filename}")

        # Check if file has a valid extension
        allowed_extensions = {".swc", ".h5", ".asc"}
        file_extension = (
            f".{file.filename.split('.')[-1].lower()}" if file.filename else ""
        )

        if not file.filename or file_extension not in allowed_extensions:
            L.error(f"Invalid file extension: {file_extension}")
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.BAD_REQUEST,
                    "detail": f"Invalid file extension. Must be one of {', '.join(allowed_extensions)}",
                },
            )

        # Read file content
        content = None
        try:
            content = await file.read()
            if not content:
                L.error(f"Empty file uploaded: {file.filename}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={
                        "code": ApiErrorCode.BAD_REQUEST,
                        "detail": "Uploaded file is empty",
                    },
                )
        except Exception as e:
            L.error(f"Error reading file {file.filename}: {str(e)}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_SERVER_ERROR,
                    "detail": f"Error reading file: {str(e)}",
                },
            )

        # Check if file is loadable in NeuroM
        try:
            # Create a temporary file to store the uploaded content
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            # Pass the temporary file path to NeuroM
            m = nm.load_morphology(temp_file_path)
        except Exception as e:
            L.error(f"NeuroM error loading file {file.filename}: {str(e)}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_SERVER_ERROR,
                    "detail": f"NeuroM failure: {str(e)}",
                },
            )
        finally:
            # Clean up the temporary file
            if "temp_file_path" in locals():
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    L.error(f"Error deleting temporary file {temp_file_path}: {str(e)}")

        # Basic validation passed
        L.info(f"File {file.filename} passed basic validation")
        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={
                "status": "pass",
                "message": f"File {file.filename} successfully uploaded and validated",
            },
        )

    return router
