import tempfile
from typing import Annotated, Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import entitysdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitSimulationScanConfig

router = APIRouter(
    prefix="/config-validation",
    tags=["config-validation"],
    dependencies=[Depends(user_verified)],
)


class SharedStatePartial(BaseModel):
    """For validation and schema dumping."""

    smc_simulation_config: CircuitSimulationScanConfig | None = None


class ConfigValidationRequest(BaseModel):
    """Request body for config validation."""

    state: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    """Response body for config validation."""

    valid: bool


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

            # Create mock return values for write operations
            # The mock entity needs to look like a real entitysdk entity
            mock_entity = MagicMock(spec=["id"])
            mock_entity.id = uuid4()

            # Mock for Simulation entities that will be in the generated list
            mock_simulation = MagicMock(spec=entitysdk.models.Simulation)  # ty:ignore[possibly-missing-submodule]
            mock_simulation.id = uuid4()

            # Make register_entity return appropriate mocks based on what's being registered
            def register_entity_side_effect(entity: Any) -> MagicMock:
                if isinstance(entity, entitysdk.models.Simulation):  # ty:ignore[possibly-missing-submodule]
                    return mock_simulation
                return mock_entity

            # Patch only the write methods, keeping read methods intact
            with (
                patch.object(
                    db_client, "register_entity", side_effect=register_entity_side_effect
                ) as mock_register,
                patch.object(db_client, "upload_file", return_value=None) as mock_upload,
                patch.object(db_client, "update_entity", return_value=None) as mock_update,
                patch("entitysdk.models.SimulationGeneration", return_value=MagicMock()),
            ):
                with tempfile.TemporaryDirectory() as tdir:
                    grid_scan = GridScanGenerationTask(
                        form=form,
                        output_root=tdir,  # ty:ignore[invalid-argument-type]
                        coordinate_directory_option="ZERO_INDEX",
                    )
                    # Execute with real db_client but patched write methods
                    grid_scan.execute(db_client=db_client)

                    # Run full task execution to validate the complete simulation config
                    # This validates block references and all config generation logic
                    run_tasks_for_generated_scan(grid_scan, db_client=db_client, entity_cache=True)

                # Verify that patched methods were actually called
                # This ensures the mocks are not stale and writes are being intercepted
                if (
                    mock_register.call_count == 0
                    or mock_upload.call_count == 0
                    or mock_update.call_count == 0
                ):
                    raise HTTPException(  # noqa: TRY301
                        status_code=500,
                        detail=(
                            "Validation error: Expected database operations did not occur. "
                            "The validation logic may be outdated."
                        ),
                    )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error: {e!s} Please fix the outstanding errors."
        ) from e

    return ConfigValidationResponse(valid=True)
