# declared_endpoints.py
import json
from enum import Enum, auto, StrEnum
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
import entitysdk.client
import entitysdk.exception
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Dict, List, Any
import os
import inspect

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
from obi_one.scientific.validations.validation_functions import (
    MorphologyValidations,
    EntityType,
    BaseValidations,
    EntityValidationManager,
    ValidationQueue
)

from obi_one.endpoints.validation_config_page import get_validation_config_page_content

# Dictionary to store registered validation objects for easy lookup
REGISTERED_VALIDATION_OBJECTS: Dict[EntityType, BaseValidations] = {}

def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    # Initialize EntityValidationManager and register validation objects here
    # This ensures it's set up when the router is activated.
    config_dir = "validation_configs"
    EntityValidationManager.set_config_directory(config_dir)

    # Ensure the config directory exists
    os.makedirs(EntityValidationManager._config_directory, exist_ok=True)

    # Register MorphologyValidations (and any other validation classes)
    morphology_validator = MorphologyValidations()
    EntityValidationManager.register_validation_object(EntityType.cell_morphology, morphology_validator)
    REGISTERED_VALIDATION_OBJECTS[EntityType.cell_morphology] = morphology_validator

    # Example of creating a dummy config file if it doesn't exist for cell_morphology
    # This ensures the frontend has something to load initially for this type
    config_path = Path(EntityValidationManager._config_directory) / f"{EntityType.cell_morphology.value}.json"
    if not config_path.exists():
        default_config = {
            ValidationQueue.MUST_PASS_TO_UPLOAD: ["is_loadable"]
        }
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        L.info(f"Created default validation config for {EntityType.cell_morphology.value}")


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

    # --- NEW ENDPOINT FOR THE SIMPLE TEST PAGE (kept from your old file) ---
    @router.get(
        "/test_page",
        summary="Simple Test Page",
        response_class=HTMLResponse,
        status_code=HTTPStatus.OK,
    )
    async def simple_test_page():
        """
        Serves a basic HTML page displaying "Test page".
        """
        return HTMLResponse(content="<h1>Test page</h1>", status_code=HTTPStatus.OK)
    # --- END NEW ENDPOINT ---

    # --- NEW ENDPOINTS FOR VALIDATION CONFIGURATION (updated) ---

    @router.get(
        "/configure-validations-page",
        summary="Configure Validations Page",
        description="Serves the HTML page for configuring validation rules.",
        response_class=HTMLResponse,
    )
    def configure_validations_page():
        return get_validation_config_page_content()

    @router.get(
        "/get-entity-validation-config/{entity_type_str}",
        summary="Get Entity-Specific Validation Configuration",
        description="Retrieves the validation configuration for a specific entity type.",
    )
    def get_entity_validation_config(entity_type_str: str):
        try:
            entity_type = EntityType(entity_type_str)
            config_path = Path(EntityValidationManager._config_directory) / f"{entity_type.value}.json"

            if not config_path.exists():
                return JSONResponse(status_code=HTTPStatus.OK, content={}) # Return empty if no config file

            with open(config_path, "r") as f:
                config = json.load(f)
            return JSONResponse(content=config)
        except ValueError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"message": f"Invalid entity type: {entity_type_str}"}
            )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"message": "Invalid JSON format in configuration file."}
            )
        except Exception as e:
            L.error(f"Failed to read validation config for {entity_type_str}: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error reading configuration"}
            )

    @router.get(
        "/get-all-entity-validation-configs",
        summary="Get All Entity Validation Configurations",
        description="Retrieves validation configurations for all registered entity types.",
    )
    def get_all_entity_validation_configs():
        all_configs = {}
        for entity_type in EntityType: # Iterate through all known entity types
            config_path = Path(EntityValidationManager._config_directory) / f"{entity_type.value}.json"
            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        if config: # Only add if config is not empty
                            all_configs[entity_type.value] = config
                except json.JSONDecodeError:
                    L.error(f"Invalid JSON format in config file for {entity_type.value}: {config_path}")
                except Exception as e:
                    L.error(f"Error reading config for {entity_type.value}: {e}")
        return JSONResponse(content=all_configs)

    @router.post(
        "/save-validation-config",
        summary="Save Validation Configuration",
        description="Saves the validation configuration for a specific entity type.",
    )
    async def save_validation_config_endpoint(request: Request):
        try:
            config_data = await request.json()
            entity_type_str = config_data.get("entity_type")
            validation_function_name = config_data.get("validation_function")
            status = config_data.get("status")

            if not all([entity_type_str, validation_function_name, status]):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": "Missing entity_type, validation_function, or status in request."}
                )

            try:
                entity_type = EntityType(entity_type_str)
            except ValueError:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": f"Invalid entity type: {entity_type_str}"}
                )

            # Ensure the status is a valid ValidationQueue member
            # Note: ValidationQueue is now an object with attributes, not an Enum itself.
            # So, validate against its known attribute values.
            valid_statuses = [
                ValidationQueue.MUST_PASS_TO_UPLOAD,
                ValidationQueue.MUST_RUN_UPON_UPLOAD,
                ValidationQueue.MUST_PASS_TO_SIMULATE
            ]
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": f"Invalid validation status: {status}. Must be one of: {valid_statuses}"}
                )


            # Get the existing configuration for the specific entity type
            entity_config_path = Path(EntityValidationManager._config_directory) / f"{entity_type.value}.json"
            current_entity_config = {}
            if entity_config_path.exists():
                with open(entity_config_path, "r") as f:
                    try:
                        current_entity_config = json.load(f)
                    except json.JSONDecodeError:
                        L.warning(f"Existing config for {entity_type.value} is invalid JSON. Overwriting.")
                        current_entity_config = {}


            # Update the configuration
            if status not in current_entity_config:
                current_entity_config[status] = []

            if validation_function_name not in current_entity_config[status]:
                current_entity_config[status].append(validation_function_name)

            # Save the updated configuration
            with open(entity_config_path, "w") as f:
                json.dump(current_entity_config, f, indent=4)

            return JSONResponse(content={"message": f"Validation configuration for {entity_type_str} updated successfully."})

        except json.JSONDecodeError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"message": "Invalid JSON format in request body."}
            )
        except Exception as e:
            L.error(f"Failed to save validation config: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error saving configuration"}
            )

    @router.post(
        "/delete-validation-rule",
        summary="Delete Validation Rule",
        description="Deletes a specific validation rule for an entity type.",
    )
    async def delete_validation_rule_endpoint(request: Request):
        try:
            rule_data = await request.json()
            entity_type_str = rule_data.get("entity_type")
            validation_function_name = rule_data.get("validation_function")
            status = rule_data.get("status")

            if not all([entity_type_str, validation_function_name, status]):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": "Missing entity_type, validation_function, or status in request."}
                )

            try:
                entity_type = EntityType(entity_type_str)
            except ValueError:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail={"message": f"Invalid entity type: {entity_type_str}"}
                )

            entity_config_path = Path(EntityValidationManager._config_directory) / f"{entity_type.value}.json"
            current_entity_config = {}
            if entity_config_path.exists():
                with open(entity_config_path, "r") as f:
                    try:
                        current_entity_config = json.load(f)
                    except json.JSONDecodeError:
                        L.warning(f"Existing config for {entity_type.value} is invalid JSON. Cannot delete rule.")
                        raise HTTPException(
                            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                            detail={"message": f"Configuration file for {entity_type.value} is corrupted."}
                        )

            if status in current_entity_config and validation_function_name in current_entity_config[status]:
                current_entity_config[status].remove(validation_function_name)
                # If the list for a status becomes empty, remove the status key
                if not current_entity_config[status]:
                    del current_entity_config[status]

                with open(entity_config_path, "w") as f:
                    json.dump(current_entity_config, f, indent=4)
                return JSONResponse(content={"message": f"Validation rule '{validation_function_name}' removed from {entity_type_str} under {status}."})
            else:
                return JSONResponse(status_code=HTTPStatus.NOT_FOUND, content={"message": "Validation rule not found."})

        except json.JSONDecodeError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"message": "Invalid JSON format in request body."}
            )
        except Exception as e:
            L.error(f"Failed to delete validation rule: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error deleting rule"}
            )

    @router.get(
        "/get-validation-functions/{entity_type_str}",
        summary="Get Available Validation Functions",
        description="Retrieves a list of available validation functions for a given entity type.",
        response_model=List[str]
    )
    def get_available_validation_functions_endpoint(entity_type_str: str):
        try:
            entity_type = EntityType(entity_type_str)
            validation_object = REGISTERED_VALIDATION_OBJECTS.get(entity_type)
            if not validation_object:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail={"message": f"No validation object registered for entity type: {entity_type_str}"}
                )

            available_functions = validation_object.get_available_validations()
            return available_functions
        except ValueError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"message": f"Invalid entity type: {entity_type_str}"}
            )
        except Exception as e:
            L.error(f"Failed to get validation functions for {entity_type_str}: {e}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error retrieving validation functions"}
            )

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
