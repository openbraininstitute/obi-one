import asyncio
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any

import entitysdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.services.validator import run_grid_scan_validation
from obi_one.scientific.tasks.build_synaptome import MEModelSynapticModelPlacementScanConfig
from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
    CreateExtracellularRecordingArrayScanConfig,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingScanConfig
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    EModelOptimizationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # ruff: ignore[line-too-long]
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.scientific.tasks.skeletonization import SkeletonizationScanConfig
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationScanConfig,
)

if TYPE_CHECKING:
    from obi_one.core.scan_config import ScanConfig

router = APIRouter(
    prefix="/config-validation",
    tags=["config-validation"],
    dependencies=[Depends(user_verified)],
)


class _SharedStatePartialBase(BaseModel):
    """All validatable config fields. Each is optional — validate whichever are present."""

    circuit_simulation_config: CircuitSimulationScanConfig | None = None
    me_model_simulation_config: MEModelSimulationScanConfig | None = None
    me_model_with_synapses_simulation_config: (
        MEModelWithSynapsesCircuitSimulationScanConfig | None
    ) = None
    ion_channel_model_simulation_config: IonChannelModelSimulationScanConfig | None = None
    skeletonization_config: SkeletonizationScanConfig | None = None
    em_synapse_mapping_config: EMSynapseMappingScanConfig | None = None
    # Build > Ion Channel. Distinct from ion_channel_model_simulation_config above, which
    # simulates an existing model; this one fits a new model from experimental traces.
    ion_channel_fitting_config: IonChannelFittingScanConfig | None = None
    me_model_synaptic_model_placement_config: MEModelSynapticModelPlacementScanConfig | None = None
    create_extracellular_recording_array_config: (
        CreateExtracellularRecordingArrayScanConfig | None
    ) = None
    synapse_parameterization_config: SynapseParameterizationScanConfig | None = None


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
    # False mirrors the generate-endpoint registration in app/endpoints/scan_config.py, so
    # validation is no stricter than generation. Generation still resolves the input recording
    # against the database; only the fitting task itself (NWB download, nrnivmodl) is skipped.
    "ion_channel_fitting_config": False,
    # Same reasoning as ion_channel_fitting_config above: these all do real I/O/compute
    # (circuit registration, mod-file writes/compilation, electrode-weight computation)
    # that generation already skips validity on; structural validation only.
    "me_model_synaptic_model_placement_config": False,
    "create_extracellular_recording_array_config": False,
    "synapse_parameterization_config": False,
}


# Optimize > E-Model optimization. EModelOptimizationScanConfig is None without the optional
# `emodel` extra, and `None | None` raises TypeError while the class body is evaluated, which
# would stop the service starting. Same conditional idiom as app/endpoints/scan_config.py. The
# field and its _VALIDATION_CONFIG entry must stay gated together, or the key is parsed and
# then never validated.
if EModelOptimizationScanConfig is not None:

    class SharedStatePartial(_SharedStatePartialBase):
        """Validatable config fields, including E-Model optimization."""

        emodel_optimization_config: EModelOptimizationScanConfig | None = None  # ty:ignore[invalid-type-form]

    # False mirrors the generate endpoint. Generation still resolves the referenced entities;
    # only the BluePyEModel/NEURON run is skipped.
    _VALIDATION_CONFIG["emodel_optimization_config"] = False
else:
    SharedStatePartial = _SharedStatePartialBase


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
    for field_name, result in zip(field_names, results, strict=True):
        if isinstance(result, BaseException):
            errors[field_name] = f"Unexpected error: {result!s}"
        elif result is not None:
            errors[field_name] = result

    if errors:
        raise HTTPException(
            status_code=400,
            detail=ConfigValidationResponse(valid=False, errors=errors).model_dump(),
        )

    return ConfigValidationResponse(valid=True, errors={})
