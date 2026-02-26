import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionScanConfig
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologyScanConfig,
    ContributeSubjectScanConfig,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    MEModelSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
)
from obi_one.scientific.tasks.schema_example import SchemaExampleScanConfig
from obi_one.scientific.tasks.skeletonization import SkeletonizationScanConfig
from obi_one.scientific.unions.aliases import SimulationsForm
import entitysdk

router = APIRouter(
    prefix="/config-validation",
    tags=["config-validation"],
    dependencies=[Depends(user_verified)],
)

# CLASS_NAME_MAP: dict[str, type] = {
#     "CircuitExtractionScanConfig": CircuitExtractionScanConfig,
#     "ContributeMorphologyScanConfig": ContributeMorphologyScanConfig,
#     "ContributeSubjectScanConfig": ContributeSubjectScanConfig,
#     "CircuitSimulationScanConfig": CircuitSimulationScanConfig,
#     "MEModelSimulationScanConfig": MEModelSimulationScanConfig,
#     "MEModelWithSynapsesCircuitSimulationScanConfig": MEModelWithSynapsesCircuitSimulationScanConfig,  # noqa: E501
#     "IonChannelFittingScanConfig": IonChannelFittingScanConfig,
#     "MorphologyMetricsScanConfig": MorphologyMetricsScanConfig,
#     "SchemaExampleScanConfig": SchemaExampleScanConfig,
#     "SkeletonizationScanConfig": SkeletonizationScanConfig,
#     "SimulationsForm": SimulationsForm,
# }

class SharedStatePartial(BaseModel):
    """For validation and schema dumping."""

    smc_simulation_config: CircuitSimulationScanConfig | None = None

# Map of which scan configs should execute single config tasks
# This mirrors the configuration in app/endpoints/scan_config.py activate_scan_config_endpoints()
EXECUTE_SINGLE_CONFIG_TASK_MAP: dict[str, bool] = {
    "CircuitSimulationScanConfig": True,
    "MEModelSimulationScanConfig": True,
    "MEModelWithSynapsesCircuitSimulationScanConfig": True,
    "MorphologyMetricsScanConfig": True,
    "ContributeMorphologyScanConfig": True,
    "ContributeSubjectScanConfig": True,
    "IonChannelFittingScanConfig": False,
    "CircuitExtractionScanConfig": False,
    "SkeletonizationScanConfig": False,
    "SchemaExampleScanConfig": False,
}

ScanConfigClassName = Literal[
    "CircuitExtractionScanConfig",
    "ContributeMorphologyScanConfig",
    "ContributeSubjectScanConfig",
    "CircuitSimulationScanConfig",
    "MEModelSimulationScanConfig",
    "MEModelWithSynapsesCircuitSimulationScanConfig",
    "IonChannelFittingScanConfig",
    "MorphologyMetricsScanConfig",
    "SchemaExampleScanConfig",
    "SkeletonizationScanConfig",
    "SimulationsForm",
]


class ConfigValidationRequest(BaseModel):
    """Request body for config validation."""

    state: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    """Response body for config validation."""

    valid: bool
    message: str


@router.post(
    "/validate",
    summary="Validate scan config data",
    description="Instantiate a scan config class and return validation results.",
)
def validate_config(
    request: ConfigValidationRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> ConfigValidationResponse:
    """Validate arbitrary data against a scan config class."""
    try:
        # Validate the state which contains the config
        state = SharedStatePartial(**request.state)
        # If we have a simulation config, try to instantiate a scan and run it
        if state.smc_simulation_config is not None:
            form = state.smc_simulation_config
            # FastAPI already validated this when parsing the request
            # Create mock return values for write operations
            # The mock entity needs to look like a real entitysdk entity
            mock_entity = MagicMock(spec=['id'])
            mock_entity.id = uuid4()  # Use a valid UUID instead of a string
            
            # Mock for Simulation entities that will be in the generated list
            mock_simulation = MagicMock(spec=entitysdk.models.Simulation)
            mock_simulation.id = uuid4()
            
            # CircuitSimulationScanConfig should execute single config tasks
            execute_single_config_task = True
            
            # Patch only the write methods, keeping read methods intact
            with patch.object(db_client, 'register_entity') as mock_register, \
                patch.object(db_client, 'upload_file', return_value=None), \
                patch.object(db_client, 'update_entity', return_value=None), \
                patch('entitysdk.models.SimulationGeneration', return_value=MagicMock()):
                
                # Make register_entity return appropriate mocks based on what's being registered
                def register_entity_side_effect(entity):
                    if isinstance(entity, entitysdk.models.Simulation):
                        return mock_simulation
                    else:
                        return mock_entity
                
                mock_register.side_effect = register_entity_side_effect
                
                with tempfile.TemporaryDirectory() as tdir:
                    grid_scan = GridScanGenerationTask(
                        form=form,
                        output_root=tdir,
                        coordinate_directory_option="ZERO_INDEX",
                    )
                    # Execute with real db_client but patched write methods
                    grid_scan.execute(db_client=db_client)
                    
                    # Also run the tasks for generated scan to match real endpoint behavior
                    if execute_single_config_task:
                        run_tasks_for_generated_scan(
                            grid_scan, 
                            db_client=db_client, 
                            entity_cache=True
                        )
            
    except ValidationError as e:
        # Pydantic validation error - format nicely
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=error_msg) from e
        
    except Exception as e:
        # Any other error during validation
        error_msg = str(e)
        
        # Handle different exception formats
        if len(e.args) == 1:
            error_msg = str(e.args[0])
        elif len(e.args) > 1:
            error_msg = str(e.args)
        
        raise HTTPException(status_code=500, detail=error_msg) from e

    return ConfigValidationResponse(valid=True, message="ok")
