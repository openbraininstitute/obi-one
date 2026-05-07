import asyncio
import tempfile
from functools import partial
from typing import Annotated, Any
from unittest.mock import MagicMock
from uuid import uuid4

import entitysdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_config import ScanConfig
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingScanConfig
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitSimulationScanConfig
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.me_model import (
    MEModelSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.me_model_with_synapses import (
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.skeletonization import SkeletonizationScanConfig

router = APIRouter(
    prefix="/config-validation",
    tags=["config-validation"],
    dependencies=[Depends(user_verified)],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SharedStatePartial(BaseModel):
    """All validatable config fields. Each is optional — validate whichever are present."""

    # Simulations (execute_single_config_task=True)
    circuit_simulation_config: CircuitSimulationScanConfig | None = None
    me_model_simulation_config: MEModelSimulationScanConfig | None = None
    me_model_with_synapses_simulation_config: MEModelWithSynapsesCircuitSimulationScanConfig | None = None
    ion_channel_model_simulation_config: IonChannelModelSimulationScanConfig | None = None

    # Processing (execute_single_config_task=False)
    skeletonization_config: SkeletonizationScanConfig | None = None
    em_synapse_mapping_config: EMSynapseMappingScanConfig | None = None


class ConfigValidationRequest(BaseModel):
    """Request body for config validation."""

    state: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    """Response body for config validation."""

    valid: bool
    errors: dict[str, str]


# ---------------------------------------------------------------------------
# Write-intercepting client (thread-safe mock for validation)
# ---------------------------------------------------------------------------


class _WriteInterceptingClient:
    """A wrapper around entitysdk.client.Client that intercepts write operations.

    Read operations are delegated to the real client.
    Write operations (register_entity, upload_file, update_entity) return mocks.
    This is thread-safe because each validator gets its own wrapper instance.
    """

    def __init__(self, real_client: entitysdk.client.Client):
        self._real_client = real_client
        self.register_call_count = 0
        self.upload_call_count = 0
        self.update_call_count = 0

    def register_entity(self, entity: Any) -> MagicMock:
        self.register_call_count += 1
        if isinstance(entity, entitysdk.models.Simulation):  # ty:ignore[possibly-missing-submodule]
            mock = MagicMock(spec=entitysdk.models.Simulation)  # ty:ignore[possibly-missing-submodule]
            mock.id = uuid4()
            return mock
        mock = MagicMock(spec=["id"])
        mock.id = uuid4()
        return mock

    def upload_file(self, *args: Any, **kwargs: Any) -> None:
        self.upload_call_count += 1
        return None

    def update_entity(self, *args: Any, **kwargs: Any) -> None:
        self.update_call_count += 1
        return None

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attribute access (reads) to the real client."""
        return getattr(self._real_client, name)


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


def _run_grid_scan_validation(
    config: ScanConfig,
    db_client: entitysdk.client.Client,
    *,
    execute_single_config_task: bool,
) -> str | None:
    """Run the standard grid scan validation flow.

    This mirrors what the /generated/* endpoints do:
    1. GridScanGenerationTask.execute() — always
    2. run_tasks_for_generated_scan() — only if execute_single_config_task=True

    Returns an error string or None if valid.
    """
    try:
        mock_client = _WriteInterceptingClient(db_client)

        with tempfile.TemporaryDirectory() as tdir:
            grid_scan = GridScanGenerationTask(
                form=config,
                output_root=tdir,  # ty:ignore[invalid-argument-type]
                coordinate_directory_option="ZERO_INDEX",
            )
            grid_scan.execute(db_client=mock_client)  # ty:ignore[invalid-argument-type]

            if execute_single_config_task:
                run_tasks_for_generated_scan(grid_scan, db_client=mock_client, entity_cache=True)  # ty:ignore[invalid-argument-type]

        # Sanity check: register_entity and upload_file must have been called
        if mock_client.register_call_count == 0 or mock_client.upload_call_count == 0:
            return (
                "Validation error: Expected database operations did not occur. "
                "The validation logic may be outdated."
            )

        # If tasks were executed, update_entity should also have been called
        if execute_single_config_task and mock_client.update_call_count == 0:
            return (
                "Validation error: Expected update operations did not occur. "
                "The validation logic may be outdated."
            )
    except Exception as e:
        return str(e)

    return None


# ---------------------------------------------------------------------------
# Registry: (field_name, execute_single_config_task)
#
# Maps each SharedStatePartial field to whether run_tasks_for_generated_scan
# should be called. This mirrors the tuples in scan_config.py's
# activate_scan_config_endpoints().
# ---------------------------------------------------------------------------

_VALIDATION_CONFIG: dict[str, bool] = {
    "circuit_simulation_config": True,
    "me_model_simulation_config": True,
    "me_model_with_synapses_simulation_config": True,
    "ion_channel_model_simulation_config": True,
    "skeletonization_config": False,
    "em_synapse_mapping_config": False,
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/validate",
    summary="Validate scan config data",
    description=(
        "Validate one or more scan config fields present in the state. "
        "All present configs are validated in parallel. "
        "Returns per-field errors for any that fail."
    ),
)
async def validate_config(
    request: ConfigValidationRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> ConfigValidationResponse:
    """Validate arbitrary data against scan config classes."""
    try:
        state = SharedStatePartial(**request.state)
    except Exception as e:
        raise HTTPException(
            status_code=422, detail=f"Invalid state structure: {e!s}"
        ) from e

    # Determine which validations to run based on non-None fields
    validations: dict[str, tuple[ScanConfig, bool]] = {}
    for field_name, execute_single_config_task in _VALIDATION_CONFIG.items():
        config_value = getattr(state, field_name, None)
        if config_value is not None:
            validations[field_name] = (config_value, execute_single_config_task)

    if not validations:
        return ConfigValidationResponse(valid=True, errors={})

    # Run all validations concurrently in the default thread pool
    loop = asyncio.get_event_loop()
    field_names = list(validations.keys())
    tasks = [
        loop.run_in_executor(
            None,
            partial(
                _run_grid_scan_validation,
                config,
                db_client,
                execute_single_config_task=execute_task,
            ),
        )
        for config, execute_task in validations.values()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors: dict[str, str] = {}
    for field_name, result in zip(field_names, results):
        if isinstance(result, Exception):
            errors[field_name] = f"Unexpected error: {result!s}"
        elif result is not None:
            errors[field_name] = result

    if errors:
        raise HTTPException(
            status_code=400,
            detail=ConfigValidationResponse(valid=False, errors=errors).model_dump(),
        )

    return ConfigValidationResponse(valid=True, errors={})
