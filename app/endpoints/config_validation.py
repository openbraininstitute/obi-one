import asyncio
from functools import partial
from typing import Annotated, Any

import entitysdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.services.validator import run_grid_scan_validation
from obi_one.core.scan_config import ScanConfig
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


class SharedStatePartial(BaseModel):
    """All validatable config fields. Each is optional — validate whichever are present."""

    # Simulations (execute_single_config_task=True)
    circuit_simulation_config: CircuitSimulationScanConfig | None = None
    me_model_simulation_config: MEModelSimulationScanConfig | None = None
    me_model_with_synapses_simulation_config: (
        MEModelWithSynapsesCircuitSimulationScanConfig | None
    ) = None
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


_VALIDATION_CONFIG: dict[str, bool] = {
    "circuit_simulation_config": True,
    "me_model_simulation_config": True,
    "me_model_with_synapses_simulation_config": True,
    "ion_channel_model_simulation_config": True,
    "skeletonization_config": False,
    "em_synapse_mapping_config": False,
}


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
        raise HTTPException(status_code=422, detail=f"Invalid state structure: {e!s}") from e

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
                run_grid_scan_validation,
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
