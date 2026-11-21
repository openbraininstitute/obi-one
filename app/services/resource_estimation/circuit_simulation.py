import math

from entitysdk import Client, models
from entitysdk.types import AssetLabel

from app.errors import ApiError, ApiErrorCode
from app.mappings import CLUSTER_INSTANCES_INFO
from app.schemas.task import ClusterResources, LaunchableTaskDefinition, TaskLaunchSubmit
from obi_one.db_sdk import db_sdk

# This was chosen based off the simulations run and recorded here:
# https://openbraininstitute.sharepoint.com/:x:/s/OpenBrainInstitute/IQBgZ53Oe1GhQZQOjc6b_NqlAfobEWCRSznthvhc3X4CHZA?e=ayfe1a
# The lowest `Mem(GB) / cell` was ~ 0.025, so a bit of margin was chosen
# to allow for the variations in connectivity.
# TODO: Temporary 3x (0.03 -> 0.09) until a better CA3-projections heuristic exists.
MEM_GB_PER_CELL = 0.09

# Memory per item, fitted on 18 single-rank NEURON runs of rCA1 and SSCX circuits within 8%
# (openbraininstitute/prod-circuit-simulation#265).
GB_PER_CELL = 0.0055  # A cell without its synapses
GB_PER_SYNAPSE = 3.0e-6  # A synapse, with the replay of its connection
CORENEURON_FACTOR = 2.5  # The CoreNEURON copy: the top of the 1.5-2.5x documented by neurodamus
MARGIN = 1.25  # Headroom over the fit, which is off by -2% to +14%
USABLE_FRACTION = 0.85  # The share of a node's memory left to the simulation


def _synapse_memory_gb(config: models.Simulation, db_client: Client) -> float:
    """The memory of a simulation from its synapses, or 0 if they were not counted."""
    number_synapses = getattr(config, "number_synapses", None)
    if number_synapses is None:
        return 0.0
    simulation_config = db_sdk.select_json_asset_content(
        client=db_client, entity=config, selection={"label": AssetLabel.sonata_simulation_config}
    )
    factor = CORENEURON_FACTOR if simulation_config.get("target_simulator") == "CORENEURON" else 1
    return (
        MARGIN * factor * (GB_PER_CELL * config.number_neurons + GB_PER_SYNAPSE * number_synapses)
    )


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: Client,
    task_definition: LaunchableTaskDefinition,
    compute_cell: str,
) -> ClusterResources:
    if compute_cell not in CLUSTER_INSTANCES_INFO:
        raise ApiError(
            message=(
                f"There is no cluster isntance info declared for compute_cell '{compute_cell}'"
            ),
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
        )

    config = db_client.get_entity(
        entity_id=json_model.config_id,
        entity_type=models.Simulation,
    )
    number_of_neurons = config.number_neurons

    # get instance types that support the neuron number in ascending order
    instances = sorted(
        [
            info
            for info in CLUSTER_INSTANCES_INFO[compute_cell]
            if info.max_neurons >= number_of_neurons
        ],
        key=lambda o: o.max_neurons,
    )

    if not instances:
        raise ApiError(
            message=(
                "No cluster instances are available that can support simulations "
                f"with {number_of_neurons} neurons. Available instances: {CLUSTER_INSTANCES_INFO}"
            ),
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
        )

    instance = instances[0]
    n_nodes = max(
        math.ceil(MEM_GB_PER_CELL * number_of_neurons / instance.memory_per_instance_gb),
        math.ceil(
            _synapse_memory_gb(config, db_client)
            / (USABLE_FRACTION * instance.memory_per_instance_gb)
        ),
    )
    instance_type = instance.name

    return task_definition.resources.model_copy(
        update={
            "instances": n_nodes,
            "instance_type": instance_type,
            "compute_cell": compute_cell,
        }
    )  # ty:ignore[invalid-return-type]
