"""Resource estimation for circuit simplification tasks.

Estimates cores, memory, and time limit based on the input circuit's
biophysical node count and edge count, plus the selected algorithm type.

Only ``single_compartment`` performs expensive per-cell filter computation
(Rossert kernels). Point-neuron algorithms (lif, adex, izhikevich, glif, gif)
skip filter computation entirely and are much cheaper.

Constants below are conservative placeholders pending empirical
calibration on a real circuit. TODO: calibrate WORK_UNITS_PER_CORE,
PER_WORKER_GB, and WORK_UNITS_PER_CORE_HOUR on a representative
circuit at 1/4/8 workers and update.
"""

import json

import entitysdk
import numpy as np
from entitysdk import models

from app.schemas.accounting import AccountingParameters
from app.schemas.task import Resources, TaskDefinition, TaskLaunchSubmit
from obi_one import deserialize_obi_object_from_json_data
from obi_one.core.registry import task_registry
from obi_one.db_sdk import db_sdk
from obi_one.scientific.library.circuit_metrics import (
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)

# --- Calibration constants (PLACEHOLDERS - TODO: calibrate empirically) ---

# Filter-based work units per core: how many (n_bio x locations) units one
# core can process in the timelimit. Only applies to single_compartment.
FILTER_WORK_UNITS_PER_CORE = 50_000

# Point-neuron work units per core: much cheaper (no filter computation).
# Calibration is per-cell emodel fitting, roughly 10x faster than filters.
POINT_NEURON_WORK_UNITS_PER_CORE = 500_000

# Memory per worker process (GB). The pipeline uses spawn-based
# multiprocessing, so each worker has its own Python interpreter + NEURON.
PER_WORKER_GB = 2.0

# Base memory for the main process + input circuit loading (GB).
BASE_MEMORY_GB = 2.0

# Work units per core-hour: used to estimate timelimit.
FILTER_WORK_UNITS_PER_CORE_HOUR = 100_000
POINT_NEURON_WORK_UNITS_PER_CORE_HOUR = 500_000

# Default max_filter_locations (matches the pipeline default).
DEFAULT_MAX_FILTER_LOCATIONS = 100

# Algorithms that require filter computation (expensive)
FILTER_ALGORITHMS = {"single_compartment"}


def _get_required_cpu_memory_combo(min_cores: int, mem_gb_required: float) -> tuple[int, int]:
    """Returns a CPU/memory preset that satisfies both core and memory requirements.

    The launch-system presets bundle CPU counts with memory tiers. This function
    finds the smallest preset that has **at least** ``min_cores`` CPUs AND
    **at least** ``mem_gb_required`` GB of memory, ensuring the workload gets
    enough compute resources (not just memory).

    Args:
        min_cores: Minimum number of CPUs required by the workload.
        mem_gb_required: Minimum memory (GB) required.

    Returns:
        A (ncpu, mem_gb) tuple from the available presets.

    Raises:
        ValueError: If no preset satisfies both constraints.
    """
    cpu_memory_combinations: dict[int, set[int]] = {
        1: {2, 4, 6, 8},
        2: {4, 8, 12, 16},
        4: {8, 16, 24, 30},
        8: {16, 32, 48, 60},
        16: {32, 64, 96, 120},
    }

    # Find all presets that satisfy both constraints
    candidates: list[tuple[int, int]] = []
    for ncpu, mem_values in cpu_memory_combinations.items():
        if ncpu < min_cores:
            continue
        for mem in sorted(mem_values):
            if mem >= mem_gb_required:
                candidates.append((ncpu, mem))
                break  # smallest mem tier for this CPU count

    if not candidates:
        max_cpu = max(cpu_memory_combinations)
        max_mem = max(cpu_memory_combinations[max_cpu])
        msg = (
            f"No CPU/memory combination found"
            f" (required: >={min_cores} cores, >={mem_gb_required:.1f} GB,"
            f" max available: {max_cpu} cores, {max_mem:.1f} GB)!"
        )
        raise ValueError(msg)

    # Return the smallest preset that satisfies both
    return min(candidates)


def estimate_task_resources(  # ruff: ignore[too-many-locals]
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: TaskDefinition,
    compute_cell: str,
    accounting_parameters: AccountingParameters | None = None,  # ruff: ignore[unused-function-argument]
) -> Resources:
    """Estimate machine resources for a circuit simplification task.

    Uses an inverted sizing model: cores are derived from the workload
    (n_bio x max_filter_locations for filter algorithms, n_bio for
    point-neuron algorithms), then memory is computed as
    base + cores x per_worker_gb.

    The algorithm blocks are read from the root ``algorithms`` dictionary. Each
    block exposes its stable compound algorithm name; only ``single_compartment``
    triggers filter computation.
    """
    # Get simplification config
    config_type = models.TaskConfig
    config = db_client.get_entity(
        entity_id=json_model.config_id,
        entity_type=config_type,
    )
    config_asset_id = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=config,
        asset_label=task_registry.get_task_type_config_asset_label(task_definition.task_type),  # ty:ignore[invalid-argument-type]
    ).id
    if config_asset_id is None:
        msg = "Config asset must have an id"
        raise ValueError(msg)

    json_str = db_client.download_content(
        entity_id=json_model.config_id,
        entity_type=config_type,
        asset_id=config_asset_id,
    ).decode(encoding="utf-8")

    json_dict = json.loads(json_str)
    single_config = deserialize_obi_object_from_json_data(json_dict)

    # Get parent circuit metrics
    circuit_id = config.inputs[0].id  # ty:ignore[not-subscriptable]
    level_of_detail_nodes_dict = {"_ALL_": CircuitStatsLevelOfDetail.basic}
    level_of_detail_edges_dict = {"_ALL_": CircuitStatsLevelOfDetail.basic}
    circuit_metrics = get_circuit_metrics(
        circuit_id=str(circuit_id),
        db_client=db_client,
        level_of_detail_nodes=level_of_detail_nodes_dict,
        level_of_detail_edges=level_of_detail_edges_dict,
    )

    # Count biophysical nodes (the population being simplified)
    nbio = int(
        np.sum([npop.number_of_nodes for npop in circuit_metrics.biophysical_node_populations])  # ty:ignore[unresolved-attribute]
    )

    # Determine algorithm type from the selected algorithm blocks. The block's
    # algorithm_name is the OBI-One compound name (for example, "adex_nest").
    algorithms = getattr(single_config, "algorithms", {})
    if isinstance(algorithms, dict):
        algorithm_names = [algorithm.algorithm_name for algorithm in algorithms.values()]
    else:
        # Keep the estimator tolerant of older in-memory configs while persisted
        # configs migrate to the root block-dictionary shape.
        legacy_simplification = getattr(single_config, "simplification", None)
        legacy_algorithms = getattr(legacy_simplification, "algorithms", algorithms)
        algorithm_names = [
            value if isinstance(value, str) else value.algorithm_name
            for value in legacy_algorithms
        ]
    base_algorithms = [
        name.removesuffix("_nest").removesuffix("_brian2")
        for name in algorithm_names
    ]
    has_filter_algo = any(a in FILTER_ALGORITHMS for a in base_algorithms)

    # Estimate work units based on algorithm type
    if has_filter_algo:
        # Filter-based: work is n_bio x max_filter_locations
        # (filter cache key is per-cell, so work is linear in this product)
        max_locations = DEFAULT_MAX_FILTER_LOCATIONS
        work_units = nbio * max_locations
        work_per_core = FILTER_WORK_UNITS_PER_CORE
        work_per_core_hour = FILTER_WORK_UNITS_PER_CORE_HOUR
    else:
        # Point-neuron: no filter computation, much cheaper per cell
        work_units = nbio
        work_per_core = POINT_NEURON_WORK_UNITS_PER_CORE
        work_per_core_hour = POINT_NEURON_WORK_UNITS_PER_CORE_HOUR

    # Inverted sizing: cores from workload first
    ncpu_required = max(1, int(np.ceil(work_units / work_per_core)))
    ncpu_required = min(ncpu_required, 16)  # cap at 16 cores (launch-system max)

    # Memory: base + cores x per_worker
    mem_gb_required = BASE_MEMORY_GB + ncpu_required * PER_WORKER_GB

    # Find a preset that satisfies BOTH core and memory requirements
    ncpu, mem_gb = _get_required_cpu_memory_combo(ncpu_required, mem_gb_required)

    # Time limit: work_units / (cores x work_per_core_hour)
    time_h = max(1, int(np.ceil(work_units / (ncpu * work_per_core_hour))))

    return task_definition.resources.model_copy(
        update={
            "cores": ncpu,
            "memory": mem_gb,
            "timelimit": f"{time_h:02d}:00",
            "compute_cell": compute_cell,
        }
    )
