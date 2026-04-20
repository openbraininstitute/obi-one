import json

import entitysdk
import numpy as np
from entitysdk import models

from app.schemas.task import Resources, TaskDefinition, TaskLaunchSubmit
from obi_one import deserialize_obi_object_from_json_data
from obi_one.scientific.library.circuit_metrics import (
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.unions.config_task_map import get_task_type_config_asset_label
from obi_one.utils import db_sdk


def _get_required_cpu_memory_combo(mem_gb_required: float) -> tuple[int, int]:
    """Returns the required CPU/memory combination."""
    # From launch-system
    cpu_memory_combinations: dict[int, set[int]] = {
        1: {2, 4, 6, 8},
        2: {4, 8, 12, 16},
        4: {8, 16, 24, 30},
        8: {16, 32, 48, 60},
        16: {32, 64, 96, 120},
    }

    max_mem = 0
    for ncpu, mem_values in cpu_memory_combinations.items():
        for mem in sorted(mem_values):
            max_mem = max(max_mem, mem)
            if mem > mem_gb_required:
                return (ncpu, mem)
    msg = (
        f"No CPU/memory combination found"
        f" (required: {mem_gb_required:.1f} GB, available: {max_mem:.1f} GB)!"
    )
    raise ValueError(msg)


def _check_available_disk_space(disk_space_gb_required: float) -> None:
    """Checks if the required disk space is available."""
    # From launch-system
    disk_space_limit_gb = 20

    if disk_space_gb_required > disk_space_limit_gb:
        msg = (
            f"Not enough disk space"
            f" (required: {disk_space_gb_required:.1f} GB,"
            f" available: {disk_space_limit_gb:.1f} GB)!"
        )
        raise ValueError(msg)


def estimate_task_resources(  # noqa: PLR0914
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: TaskDefinition,
    compute_cell: str,
) -> Resources:
    """Estimate machine resources for a circuit extraction task."""
    # Get extraction config
    config_type = models.TaskConfig
    config = db_client.get_entity(
        entity_id=json_model.config_id,
        entity_type=config_type,
    )
    config_asset_id = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=config,
        asset_label=get_task_type_config_asset_label(task_definition.task_type),
    ).id

    json_str = db_client.download_content(
        entity_id=json_model.config_id,
        entity_type=config_type,
        asset_id=config_asset_id,
    ).decode(encoding="utf-8")

    json_dict = json.loads(json_str)
    single_config = deserialize_obi_object_from_json_data(json_dict)

    # Get parent circuit metrics
    circuit_id = config.inputs[0].id
    level_of_detail_nodes_dict = {"_ALL_": CircuitStatsLevelOfDetail.basic}
    level_of_detail_edges_dict = {"_ALL_": CircuitStatsLevelOfDetail.basic}
    circuit_metrics = get_circuit_metrics(
        circuit_id=str(circuit_id),
        db_client=db_client,
        level_of_detail_nodes=level_of_detail_nodes_dict,
        level_of_detail_edges=level_of_detail_edges_dict,
    )

    # Estimate memory based on the number of input neurons
    nbio = np.sum([npop.number_of_nodes for npop in circuit_metrics.biophysical_node_populations])
    nvirt = np.sum([npop.number_of_nodes for npop in circuit_metrics.virtual_node_populations])
    input_size_neurons = (nbio + nvirt) if single_config.initialize.do_virtual else nbio

    mem_gb_required = 1 + 55e-6 * input_size_neurons
    ncpu, mem_gb = _get_required_cpu_memory_combo(mem_gb_required)

    # Estimate time limit based on the number input neurons
    time_h = np.ceil(input_size_neurons * 5e-6).astype(int)

    # Estimate disk space based in the number of input synapses
    sbio = np.sum(
        [
            epop.number_of_edges
            for epop in circuit_metrics.chemical_edge_populations
            if epop.source_name in circuit_metrics.names_of_biophys_node_populations
        ]
    )
    svirt = np.sum(
        [
            epop.number_of_edges
            for epop in circuit_metrics.chemical_edge_populations
            if epop.source_name in circuit_metrics.names_of_virtual_node_populations
        ]
    )
    input_size_synapses = (sbio + svirt) if single_config.initialize.do_virtual else sbio
    output_size_synapses = input_size_synapses  # Using maximum output count
    output_size_gb = 1 + output_size_synapses * 1.85e-7
    _check_available_disk_space(output_size_gb)

    # Update resources
    return task_definition.resources.model_copy(
        update={
            "cores": ncpu,
            "memory": mem_gb,
            "timelimit": f"{time_h:02d}:00",
            "compute_cell": compute_cell,
        }
    )
