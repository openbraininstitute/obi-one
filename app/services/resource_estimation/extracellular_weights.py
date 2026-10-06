import json
import math
from http import HTTPStatus

import entitysdk
from entitysdk import models
from entitysdk.types import CircuitScale

from app.errors import ApiError, ApiErrorCode
from app.schemas.accounting import AccountingParameters
from app.schemas.task import LaunchableTaskDefinition, Resources, TaskLaunchSubmit
from app.services.resource_estimation.circuit_extraction import (
    MAX_MEMORY_GB,
    get_required_cpu_memory_combo,
)
from obi_one import deserialize_obi_object_from_json_data
from obi_one.core.registry import task_registry
from obi_one.db_sdk import db_sdk

SUPPORTED_CIRCUIT_SCALES = frozenset(
    {CircuitScale.single, CircuitScale.pair, CircuitScale.small, CircuitScale.microcircuit}
)

# write_weights builds every cell in one process, so memory and time scale with the cell count.
# Fitted to runs measured in #1062, budgeting every cell like an L5 pyramidal cell.
BASE_MEMORY_GB = 1.0
MEMORY_GB_PER_CELL = 0.01
MEMORY_GB_PER_CELL_AND_ELECTRODE = 3e-5
SECONDS_PER_CELL = 0.6
OVERHEAD_SECONDS = 900  # staging the circuit and compiling its mechanisms


def _count_electrodes(
    json_model: TaskLaunchSubmit,
    config: models.TaskConfig,
    db_client: entitysdk.Client,
    task_definition: LaunchableTaskDefinition,
) -> int:
    config_asset_id = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=config,
        asset_label=task_registry.get_task_type_config_asset_label(task_definition.task_type),  # ty:ignore[invalid-argument-type]
    ).id
    json_str = db_client.download_content(
        entity_id=json_model.config_id,
        entity_type=models.TaskConfig,
        asset_id=config_asset_id,
    ).decode(encoding="utf-8")
    single_config = deserialize_obi_object_from_json_data(json.loads(json_str))

    return sum(
        len(block.get_global_electrode_xyz_locations())
        for block in single_config.electrode_locations.values()  # ty:ignore[unresolved-attribute]
    )


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: LaunchableTaskDefinition,
    compute_cell: str,
    accounting_parameters: AccountingParameters | None = None,  # ruff: ignore[unused-function-argument]
) -> Resources:
    """Estimate machine resources for an extracellular recording weights calculation.

    Scales memory and time with the number of cells in the circuit and electrodes in the
    array, never below the defaults from TASK_DEFINITIONS. Circuits larger than a
    microcircuit, or too large for any machine, are rejected.
    """
    config = db_client.get_entity(entity_id=json_model.config_id, entity_type=models.TaskConfig)

    if not config.inputs:
        msg = (
            "Extracellular recording weights config has no input circuit registered; cannot "
            "estimate its resources."
        )
        raise ApiError(
            message=msg,
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    circuit = db_client.get_entity(entity_id=config.inputs[0].id, entity_type=models.Circuit)

    if circuit.scale not in SUPPORTED_CIRCUIT_SCALES:
        supported = ", ".join(
            f"'{scale.value}'" for scale in CircuitScale if scale in SUPPORTED_CIRCUIT_SCALES
        )
        msg = (
            f"Extracellular recording weights are not supported for circuits of scale"
            f" '{circuit.scale}'. Supported scales: {supported}."
        )
        raise ApiError(
            message=msg,
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    n_cells = circuit.number_neurons
    n_electrodes = _count_electrodes(json_model, config, db_client, task_definition)
    defaults = task_definition.resources

    memory_gb_required = BASE_MEMORY_GB + n_cells * (
        MEMORY_GB_PER_CELL + n_electrodes * MEMORY_GB_PER_CELL_AND_ELECTRODE
    )
    try:
        cores, memory_gb = get_required_cpu_memory_combo(memory_gb_required)
    except ValueError as e:
        # Fewer electrodes only helps if the cells alone would fit.
        hint = (
            "Use fewer electrodes or a smaller circuit."
            if BASE_MEMORY_GB + n_cells * MEMORY_GB_PER_CELL < MAX_MEMORY_GB
            else "Use a smaller circuit."
        )
        msg = (
            f"Calculating extracellular recording weights for '{circuit.name}' ({n_cells:,} cells,"
            f" {n_electrodes:,} electrodes) needs about {memory_gb_required:.0f} GB of memory, more"
            f" than the largest machine has ({MAX_MEMORY_GB} GB). {hint}"
        )
        raise ApiError(
            message=msg,
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from e
    # Small circuits keep the defaults, which also cover compiling the mechanisms.
    if memory_gb < defaults.memory:  # ty:ignore[unresolved-attribute]
        cores, memory_gb = defaults.cores, defaults.memory  # ty:ignore[unresolved-attribute]

    default_hours = int(defaults.timelimit.split(":")[0])  # ty:ignore[unresolved-attribute]
    hours = max(default_hours, math.ceil((OVERHEAD_SECONDS + n_cells * SECONDS_PER_CELL) / 3600))

    return defaults.model_copy(
        update={
            "cores": cores,
            "memory": memory_gb,
            "timelimit": f"{hours:02d}:00",
            "compute_cell": compute_cell,
        }
    )
