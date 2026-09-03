import math

from entitysdk import Client, models

from app.errors import ApiError, ApiErrorCode
from app.mappings import CLUSTER_INSTANCES_INFO
from app.schemas.task import ClusterResources, TaskDefinition, TaskLaunchSubmit

# This was chosen based off the simulations run and recorded here:
# https://openbraininstitute.sharepoint.com/:x:/s/OpenBrainInstitute/IQBgZ53Oe1GhQZQOjc6b_NqlAfobEWCRSznthvhc3X4CHZA?e=ayfe1a
# The lowest `Mem(GB) / cell` was ~ 0.025, so a bit of margin was chosen
# to allow for the variations in connectivity.
MEM_GB_PER_CELL = 0.03


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: Client,
    task_definition: TaskDefinition,
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
    n_nodes = math.ceil(MEM_GB_PER_CELL * number_of_neurons / instance.memory_per_instance_gb)
    instance_type = instance.name

    return task_definition.resources.model_copy(
        update={
            "instances": n_nodes,
            "instance_type": instance_type,
            "compute_cell": compute_cell,
        }
    )  # ty:ignore[invalid-return-type]
