from http import HTTPStatus
from typing import Annotated
from enum import Enum, auto, StrEnum
import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.scientific.ephys_extraction.ephys_extraction import (
    AmplitudeInput,
    CALCULATED_FEATURES,
    ElectrophysiologyMetricsOutput,
    STIMULI_TYPES,
    get_electrophysiology_metrics,
)
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MorphologyMetricsOutput,
    get_morphology_metrics,
)
from obi_one.scientific.validations.reconstruction_morphology_validation import (
    ReconstructionMorphologyValidation,    
    AnotherValidationClass,
    YetAnotherValidationClass,    
)

# Import the new function for validation webpage content
from obi_one.endpoints.validation_config_page import get_validation_config_page_content

# Define the path to your validation config file
VALIDATION_CONFIG_PATH = Path("validation_config.json")  # Adjust this path if your file is elsewhere

#we will later import this from entitycore directly
#but entitycore has no PyPi package currently
class EntityType(StrEnum):
    """Entity types."""
    age = auto()
    analysis_software_source_code = auto()
    emodel = auto()
    experimental_bouton_density = auto()
    experimental_neuron_density = auto()
    experimental_synapses_per_connection = auto()
    memodel = auto()
    mesh = auto()
    cell_morphology = auto()
    electrical_cell_recording = auto()
    electrical_recording_stimulus = auto()
    scientific_artifact = auto()
    single_neuron_simulation = auto()
    single_neuron_synaptome = auto()
    single_neuron_synaptome_simulation = auto()
    subject = auto()
    synaptic_pathway = auto()
    
def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    @router.get(
        "/neuron-morphology-metrics/{reconstruction_morphology_id}",
        summary="Neuron morphology metrics",
        description="This calculates neuron morphology metrics for a given reconstruction \
                    morphology.",
    )
    def neuron_morphology_metrics_endpoint(
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        reconstruction_morphology_id: str,
    ) -> MorphologyMetricsOutput:
        L.info("get_morphology_metrics")

        try:
            metrics = get_morphology_metrics(
                reconstruction_morphology_id=reconstruction_morphology_id,
                db_client=db_client,
            )
        except entitysdk.exception.EntitySDKError:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": (
                        f"Reconstruction morphology {reconstruction_morphology_id} not found."
                    ),
                },
            )

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
 # --- NEW ENDPOINTS FOR VALIDATION CONFIGURATION ---
    @router.get(
        "/configure_validations_page",
        summary="Configure Validations Webpage",
        response_class=HTMLResponse,
        status_code=HTTPStatus.OK,
    )
    @router.get(
        "/available_entity_types",
        summary="Get Available Entity Types",
        response_class=JSONResponse,
        status_code=HTTPStatus.OK,
    )
    async def get_available_entity_types():
        """
        Returns a list of available entity types from the EntityType enum.
        """
        return JSONResponse({"entity_types": [e.value for e in EntityType]})


    # --- NEW ENDPOINTS FOR VALIDATION CONFIGURATION ---
    @router.get(
        "/configure_validations_page",
        summary="Configure Validations Webpage",
        response_class=HTMLResponse,
        status_code=HTTPStatus.OK,
    )
    async def configure_validations_webpage():
        """
        Serves the HTML page for editing validation configurations.
        """
        html_content = get_validation_config_page_content()
        return HTMLResponse(content=html_content, status_code=HTTPStatus.OK)

    @router.get(
        "/available_validation_functions",
        summary="Get Available Validation Functions",
        response_class=JSONResponse,
        status_code=HTTPStatus.OK,
    )
    async def get_available_validation_functions():
        """
        Returns a list of available validation function names and their associated entity types
        from predefined classes.
        """
        validation_classes = [
            ReconstructionMorphologyValidation,
            AnotherValidationClass,
            YetAnotherValidationClass,            
        ]
        function_info = []
        for cls in validation_classes:
            function_info.append({
                "name": cls.__name__,
                "entity": getattr(cls, 'entity', None)
            })
        return JSONResponse({"validation_functions": function_info})



    @router.get(
        "/validation_config",
        summary="Get Validation Configuration",
        response_class=JSONResponse,
        status_code=HTTPStatus.OK,
    )
    async def get_validation_config():
        """
        Reads and returns the current validation_config.json file.
        """
        if not VALIDATION_CONFIG_PATH.exists():
            return JSONResponse({"entity_types": {}}, status_code=HTTPStatus.OK)
        try:
            with open(VALIDATION_CONFIG_PATH, 'r') as f:
                config_data = json.load(f)
            return JSONResponse(config_data, status_code=HTTPStatus.OK)
        except json.JSONDecodeError as e:
            L.error(f"Error decoding validation_config.json: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Error decoding validation_config.json"}
            )
        except Exception as e:
            L.error(f"Failed to read validation_config.json: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error reading configuration"}
            )

    @router.post(
        "/validation_config",
        summary="Update Validation Configuration",
        response_class=JSONResponse,
        status_code=HTTPStatus.OK,
    )



    async def update_validation_config(request: Request):
        """
        Updates the validation_config.json file with new configuration.
        """
        if 1:
            new_config = await request.json()
            if "entity_types" not in new_config:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": "Invalid configuration format: 'entity_types' key missing."}
                )
            with open(VALIDATION_CONFIG_PATH, 'w') as f:
                json.dump(new_config, f, indent=2)
            return JSONResponse({"message": "Configuration updated successfully!"}, status_code=HTTPStatus.OK)
       
    
    
    @router.get(
        "/electrophysiologyrecording-metrics/{trace_id}",
        summary="electrophysiology recording metrics",
        description="This calculates electrophysiology traces metrics for a particular recording",
    )
    def electrophysiologyrecording_metrics_endpoint(
        trace_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        requested_metrics: CALCULATED_FEATURES | None = Query(default=None),
        amplitude: AmplitudeInput = Depends(),
        protocols: STIMULI_TYPES | None = Query(default=None),
    ) -> ElectrophysiologyMetricsOutput:
        try:
            ephys_metrics = get_electrophysiology_metrics(
                trace_id=trace_id,
                entity_client=db_client,
                calculated_feature=requested_metrics,
                amplitude=amplitude,
                stimuli_types=protocols,
            )
            return ephys_metrics
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

    return router
'''


    async def update_validation_config(request: Request):
        """
        Updates the validation_config.json file with new configuration.
        """
        try:
            new_config = await request.json()
            if "entity_types" not in new_config:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": "Invalid configuration format: 'entity_types' key missing."}
                )
            with open(VALIDATION_CONFIG_PATH, 'w') as f:
                json.dump(new_config, f, indent=2)
            return JSONResponse({"message": "Configuration updated successfully!"}, status_code=HTTPStatus.OK)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"message": "Invalid JSON format in request body."}
            )
        except Exception as e:
            L.error(f"Failed to write validation_config.json: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error saving configuration"}
            )

'''
