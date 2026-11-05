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
    EXTRA_DISK_SPACE_LIMIT_GB,
    MAX_MEMORY_GB,
    get_required_cpu_memory_combo,
    get_required_extra_storage_space,
)
from obi_one.core.base import OBIBaseModel
from obi_one.core.deserialize import deserialize_obi_object_from_json_data
from obi_one.core.exception import ConfigValidationError
from obi_one.core.scan_generation import ScanGenerationTask
from obi_one.core.single import SingleConfigMixin
from obi_one.db_sdk import db_sdk
from obi_one.scientific.mappings_and_registry.config_task_map import (
    get_task_spec_for_task_type,
)
from obi_one.scientific.tasks.create_recording_array.process import (
    CELLS_PER_BATCH_PER_PROCESS,
    SEGMENTS_PER_WEIGHTS_BLOCK,
    get_number_of_mpi_processes,
)

SUPPORTED_CIRCUIT_SCALES = frozenset(
    {CircuitScale.single, CircuitScale.pair, CircuitScale.small, CircuitScale.microcircuit}
)

# Each of write_weights' MPI processes loads NEURON and neurodamus, builds a batch of cells at a
# time and computes the weights a block of segments at a time; the positions of every segment
# are kept. Measured in the launch image: 0.35 GB per process, up to 7.1 MB per built cell (an
# rCA1 slice on staging), about 160 bytes per segment kept, and two float64 copies of a block.
MEMORY_GB_PER_PROCESS = 0.5
MEMORY_GB_PER_CELL = 0.01
MEMORY_GB_PER_SEGMENT = 2.5e-7
MEMORY_GB_PER_PROCESS_AND_ELECTRODE = SEGMENTS_PER_WEIGHTS_BLOCK * 2 * 8 / 1e9
# The weights file holds a float64 per segment and electrode. Cells of the nbS1 layers have
# about 300 segments, those of an rCA1 slice 582 and L5 pyramidal cells 951.
SEGMENTS_PER_CELL = 1_000
DISK_GB_FOR_JOB = 15  # the image, the job's packages and the staged circuit
# In one process. Microcircuits take 0.6 to 0.9 s, but nbS1-O1 3.1 s: its morphologies come from a
# 12.6 GB container read over the S3 mount.
SECONDS_PER_CELL = 4.0
SECONDS_PER_WEIGHTS_GB = 30  # writing, checksumming and uploading the weights file
OVERHEAD_SECONDS = 900  # staging the circuit and compiling its mechanisms


def _download_single_config(
    json_model: TaskLaunchSubmit,
    config: models.TaskConfig,
    db_client: entitysdk.Client,
    task_definition: LaunchableTaskDefinition,
) -> OBIBaseModel:
    config_asset_id = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=config,
        asset_label=get_task_spec_for_task_type(task_definition.task_type).asset_label,  # ty:ignore[invalid-argument-type]
    ).id
    json_str = db_client.download_content(
        entity_id=json_model.config_id,
        entity_type=models.TaskConfig,
        asset_id=config_asset_id,
    ).decode(encoding="utf-8")
    return deserialize_obi_object_from_json_data(json.loads(json_str))


def _count_electrodes(single_config: OBIBaseModel | SingleConfigMixin) -> int:
    return sum(
        len(block.get_global_electrode_xyz_locations())
        for block in single_config.electrode_locations.values()  # ty:ignore[unresolved-attribute]
    )


def _too_large_error(
    circuit: models.Circuit, n_cells: int, n_electrodes: int, needs: str, hint: str
) -> ApiError:
    """The error for weights that need more than the largest task can have."""
    msg = (
        f"Calculating extracellular recording weights for '{circuit.name}' ({n_cells:,} cells,"
        f" {n_electrodes:,} electrodes) {needs}. {hint}"
    )
    return ApiError(
        message=msg,
        error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
        http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def _cpus_and_memory(
    circuit: models.Circuit, n_cells: int, n_electrodes: int, min_cpus: int
) -> tuple[int, int]:
    """CPUs and memory for a process per CPU, each with its batch of cells and block of weights."""
    memory_gb_per_process = (
        MEMORY_GB_PER_PROCESS
        + CELLS_PER_BATCH_PER_PROCESS * MEMORY_GB_PER_CELL
        + n_electrodes * MEMORY_GB_PER_PROCESS_AND_ELECTRODE
    )
    memory_gb_for_segments = n_cells * SEGMENTS_PER_CELL * MEMORY_GB_PER_SEGMENT
    try:
        return get_required_cpu_memory_combo(
            memory_gb_for_segments, min_cpus=min_cpus, mem_gb_per_cpu=memory_gb_per_process
        )
    except ValueError as e:
        memory_gb_required = memory_gb_for_segments + min_cpus * memory_gb_per_process
        memory_gb_for_electrodes = min_cpus * n_electrodes * MEMORY_GB_PER_PROCESS_AND_ELECTRODE
        raise _too_large_error(
            circuit,
            n_cells,
            n_electrodes,
            needs=(
                f"needs about {memory_gb_required:.0f} GB of memory, more than the largest"
                f" machine has ({MAX_MEMORY_GB} GB)"
            ),
            # Fewer electrodes only helps if the cells alone would fit.
            hint=(
                "Use fewer electrodes or a smaller circuit."
                if memory_gb_required - memory_gb_for_electrodes < MAX_MEMORY_GB
                else "Use a smaller circuit."
            ),
        ) from e


def _weights_gb_and_storage(
    circuit: models.Circuit, n_cells: int, n_electrodes: int
) -> tuple[float, int | None]:
    """The size of the weights file, and the extra disk the task needs to write it."""
    weights_gb = n_cells * SEGMENTS_PER_CELL * n_electrodes * 8 / 1e9
    try:
        return weights_gb, get_required_extra_storage_space(DISK_GB_FOR_JOB + weights_gb)
    except ValueError as e:
        raise _too_large_error(
            circuit,
            n_cells,
            n_electrodes,
            needs=(
                f"writes a weights file of up to {weights_gb:.0f} GB, more than the"
                f" {EXTRA_DISK_SPACE_LIMIT_GB} GB of storage a task can have"
            ),
            hint="Use fewer electrodes or a smaller circuit.",
        ) from e


def _size_task(circuit: models.Circuit, n_electrodes: int) -> tuple[int, int, float, int | None]:
    """CPUs, memory, weights file size and extra disk, refusing what no task can run."""
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
    n_processes = get_number_of_mpi_processes(n_cells)
    cores, memory_gb = _cpus_and_memory(circuit, n_cells, n_electrodes, min_cpus=n_processes)
    weights_gb, storage_gb = _weights_gb_and_storage(circuit, n_cells, n_electrodes)
    return cores, memory_gb, weights_gb, storage_gb


def check_scan_resources(grid_scan: ScanGenerationTask, db_client: entitysdk.Client) -> None:
    """Refuse a scan with a coordinate the launch would refuse, before anything is registered."""
    circuits: dict[str, models.Circuit] = {}
    for single_config in grid_scan.create_single_configs():
        circuit_from_id = single_config.initialize.circuit  # ty:ignore[unresolved-attribute]
        if circuit_from_id.id_str not in circuits:
            circuits[circuit_from_id.id_str] = circuit_from_id.entity(db_client=db_client)
        try:
            _size_task(circuits[circuit_from_id.id_str], _count_electrodes(single_config))
        except ApiError as e:
            raise ConfigValidationError(e.message) from e


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: LaunchableTaskDefinition,
    compute_cell: str,
    accounting_parameters: AccountingParameters | None = None,  # ruff: ignore[unused-function-argument]
) -> Resources:
    """Estimate machine resources for an extracellular recording weights calculation.

    Asks for a CPU per 100 cells, as write_weights runs an MPI process on each CPU, memory for
    each process's batch of cells and block of weights and for every segment's position, disk
    for the weights file, and time for the cells and the file, never below the defaults from
    TASK_DEFINITIONS. Circuits larger than a microcircuit, or too large for any task, are
    rejected.
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

    n_cells = circuit.number_neurons
    single_config = _download_single_config(json_model, config, db_client, task_definition)
    cores, memory_gb, weights_gb, storage_gb = _size_task(circuit, _count_electrodes(single_config))
    defaults = task_definition.resources
    # Small circuits keep the default memory, which also covers compiling the mechanisms.
    memory_gb = max(memory_gb, defaults.memory)  # ty:ignore[unresolved-attribute]

    default_hours = int(defaults.timelimit.split(":")[0])  # ty:ignore[unresolved-attribute]
    seconds = (
        OVERHEAD_SECONDS + n_cells * SECONDS_PER_CELL / cores + weights_gb * SECONDS_PER_WEIGHTS_GB
    )
    hours = max(default_hours, math.ceil(seconds / 3600))

    return defaults.model_copy(
        update={
            "cores": cores,
            "memory": memory_gb,
            "timelimit": f"{hours:02d}:00",
            "compute_cell": compute_cell,
            "ephemeral_storage": storage_gb,
        }
    )
