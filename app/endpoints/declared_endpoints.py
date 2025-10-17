import asyncio
import pathlib
import tempfile
import zipfile
from http import HTTPStatus
from typing import Annotated, Literal

import entitysdk.client
import entitysdk.exception
import morphio
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from morph_tool import convert
from pydantic import BaseModel, Field, ValidationError

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.core.exception import ProtocolNotFoundError
from obi_one.core.parametric_multi_values import (
    MAX_N_COORDINATES,
    ParametericMultiValueUnion,
)
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsOutput,
    CircuitNodesetsResponse,
    CircuitPopulationsResponse,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.library.connectivity_metrics import (
    ConnectivityMetricsOutput,
    ConnectivityMetricsRequest,
    get_connectivity_metrics,
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
from obi_one.scientific.unions.unions_scan_configs import (
    ScanConfigsUnion,
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

    @router.get(
        "/neuron-morphology-metrics/{cell_morphology_id}",
        summary="Neuron morphology metrics",
        description=("This calculates neuron morphology metrics for a given cell morphology."),
    )
    def neuron_morphology_metrics_endpoint(
        cell_morphology_id: str,
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
                cell_morphology_id=cell_morphology_id,
                db_client=db_client,
                requested_metrics=requested_metrics,
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": (
                        f"Internal error retrieving the cell morphology {cell_morphology_id}."
                    ),
                },
            ) from err

        if metrics:
            return metrics
        L.error(f"Cell morphology {cell_morphology_id} metrics computation issue")
        raise ApiError(
            message="Internal error retrieving the asset.",
            error_code=ApiErrorCode.INTERNAL_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


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


async def _process_and_convert_morphology(
    file: UploadFile, temp_file_path: str, file_extension: str
) -> tuple[str, str]:
    """Process and convert a neuron morphology file."""
    try:
        morphio.set_raise_warnings(False)
        _ = morphio.Morphology(temp_file_path)

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
        L.error(f"Morphio error loading file {file.filename}: {e!s}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Failed to load and convert the file: {e!s}",
            },
        ) from e
    else:
        return outputfile1, outputfile2


def _create_zip_file_sync(zip_path: str, file1: str, file2: str) -> None:
    """Synchronously create a zip file from two files."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as my_zip:
        my_zip.write(file1, arcname=f"{pathlib.Path(file1).name}")
        my_zip.write(file2, arcname=f"{pathlib.Path(file2).name}")


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
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Error creating zip file: {e!s}",
            },
        ) from e
    else:
        L.info(f"Created zip file: {zip_filename}")
        return FileResponse(path=zip_filename, filename=zip_filename, media_type="application/zip")


async def _validate_and_read_file(file: UploadFile) -> tuple[bytes, str]:
    """Validates file extension and reads content."""
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

    content = await file.read()
    if not content:
        _handle_empty_file(file)

    return content, file_extension


def activate_test_endpoint(router: APIRouter) -> None:
    """Define neuron file test endpoint."""

    @router.post(
        "/test-neuron-file",
        summary="Validate morphology format and returns the conversion to other formats.",
        description="Tests a neuron file (.swc, .h5, or .asc) with basic validation.",
    )
    async def test_neuron_file(
        file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    ) -> FileResponse:
        content, file_extension = await _validate_and_read_file(file)

        temp_file_path = ""
        outputfile1, outputfile2 = "", ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            outputfile1, outputfile2 = await _process_and_convert_morphology(
                file=file, temp_file_path=temp_file_path, file_extension=file_extension
            )

            return await _create_and_return_zip(outputfile1, outputfile2)

        finally:
            if temp_file_path:
                try:
                    pathlib.Path(temp_file_path).unlink(missing_ok=True)
                    pathlib.Path(outputfile1).unlink(missing_ok=True)
                    pathlib.Path(outputfile2).unlink(missing_ok=True)
                except OSError as e:
                    L.error(f"Error deleting temporary files: {e!s}")


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
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": f"Internal error retrieving the circuit {circuit_id}.",
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
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": f"Internal error retrieving the circuit {circuit_id}.",
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
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": f"Internal error retrieving the circuit {circuit_id}.",
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
            mapped_circuit_properties = {}
            mapped_circuit_properties[CircuitPropertyType.NODE_SET] = (
                circuit_metrics.names_of_nodesets
            )

        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": f"Internal error retrieving the circuit {circuit_id}.",
                },
            ) from err
        return mapped_circuit_properties


def activate_connectivity_endpoints(router: APIRouter) -> None:
    """Define circuit-related endpoints."""

    @router.post(
        "/connectivity-metrics/{circuit_id}",
        summary="Connectivity metrics",
        description=(
            "This calculates connectivity metrics, such as connection probabilities and"
            " mean number of synapses per connection between different groups of neurons."
        ),
    )
    def connectivity_metrics_endpoint(
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        conn_request: ConnectivityMetricsRequest,
    ) -> ConnectivityMetricsOutput:
        try:
            conn_metrics = get_connectivity_metrics(
                circuit_id=conn_request.circuit_id,
                db_client=db_client,
                edge_population=conn_request.edge_population,
                pre_selection=conn_request.pre_selection,
                pre_node_set=conn_request.pre_node_set,
                post_selection=conn_request.post_selection,
                post_node_set=conn_request.post_node_set,
                group_by=conn_request.group_by,
                max_distance=conn_request.max_distance,
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": f"Internal error retrieving the circuit {conn_request.circuit_id}.",
                },
            ) from err
        return conn_metrics


def activate_scan_config_endpoint(router: APIRouter) -> dict:
    """Define scan configuration endpoints."""

    @router.post(
        "/scan_config/grid-scan-coordinate-count",
        summary="Grid scan coordinate count",
        description=("This calculates the number of coordinates for a grid scan configuration."),
    )
    def grid_scan_parameters_count_endpoint(
        scan_config: ScanConfigsUnion,
    ) -> int:
        L.info("grid_scan_parameters_endpoint")
        grid_scan = GridScanGenerationTask(
            form=scan_config,
            output_root="",
            coordinate_directory_option="ZERO_INDEX",
        )

        n_grid_scan_coordinates = np.prod(
            [len(mv.values) for mv in grid_scan.multiple_value_parameters()]
        )
        if n_grid_scan_coordinates > MAX_N_COORDINATES:
            raise HTTPException(
                status_code=400,
                detail=f"Number of grid scan coordinates {n_grid_scan_coordinates} exceeds\
                    maximum allowed {MAX_N_COORDINATES}.",
            )

        n_grid_scan_coordinates = max(1, n_grid_scan_coordinates)  # Ensure at least 1 coordinate

        return n_grid_scan_coordinates


def process_value_validation_errors(e: ValidationError) -> None:
    for err in e.errors():
        if err["type"] == "greater_than":
            raise HTTPException(
                status_code=400, detail=f"All values must be > {err['ctx'].get('gt')}"
            ) from e
        if err["type"] == "greater_than_equal":
            raise HTTPException(
                status_code=400, detail=f"All values must be ≥ {err['ctx'].get('ge')}"
            ) from e
        if err["type"] == "less_than":
            raise HTTPException(
                status_code=400, detail=f"All values must be < {err['ctx'].get('lt')}"
            ) from e
        if err["type"] == "less_than_equal":
            raise HTTPException(
                status_code=400, detail=f"All values must be ≤ {err['ctx'].get('le')}"
            ) from e
        if err["type"] == "value_error":
            raise HTTPException(status_code=400, detail=err["msg"]) from e
        if err["type"] == "custom_n_greater_than_max":
            raise HTTPException(status_code=400, detail=err["msg"]) from e


def activate_parameteric_multi_value_endpoint(router: APIRouter) -> None:
    """Fill in later."""
    model_name = "parametric-multi-value"

    # Create endpoint name
    endpoint_name_with_slash = "/" + model_name
    model_description = "Temp description."

    @router.post(endpoint_name_with_slash, summary=model_name, description=model_description)
    def endpoint(
        parameteric_multi_value_type: ParametericMultiValueUnion,
        # Query-level constraints
        ge: Annotated[
            float | int | None, Query(description="Require all values to be ≥ this")
        ] = None,
        gt: Annotated[
            float | int | None, Query(description="Require all values to be > this")
        ] = None,
        le: Annotated[
            float | int | None, Query(description="Require all values to be ≤ this")
        ] = None,
        lt: Annotated[
            float | int | None, Query(description="Require all values to be < this")
        ] = None,
    ) -> list[float] | list[int]:
        try:
            # Create class to allow static annotations with constraints
            class MultiParamHolder(BaseModel):
                multi_value_class: Annotated[
                    ParametericMultiValueUnion, Field(ge=ge, gt=gt, le=le, lt=lt)
                ]

            mvh = MultiParamHolder(
                multi_value_class=parameteric_multi_value_type
            )  # Validate constraints

        except ValidationError as e:
            process_value_validation_errors(e)

        except Exception as e:
            raise HTTPException(status_code=400, detail="Unknown Error") from e

        return list(mvh.multi_value_class)


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_morphology_endpoint(router)
    activate_ephys_endpoint(router)
    activate_test_endpoint(router)
    activate_circuit_endpoints(router)
    activate_connectivity_endpoints(router)
    activate_scan_config_endpoint(router)
    activate_parameteric_multi_value_endpoint(router)
    return router
