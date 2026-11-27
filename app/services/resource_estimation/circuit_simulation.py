import math

from entitysdk import Client, models
from entitysdk.types import AssetLabel
from pydantic import BaseModel, ConfigDict

from app.errors import ApiError, ApiErrorCode
from app.mappings import CLUSTER_INSTANCES_INFO
from app.schemas.cluster import ClusterInstanceInfo
from app.schemas.task import ClusterResources, LaunchableTaskDefinition, TaskLaunchSubmit
from obi_one.scientific.library.circuit_synapses import SUBSET_FACTOR


class MemoryModel(BaseModel):
    """Peak memory of a neurodamus simulation, in GB. See docs/circuit-simulation-resources.md."""

    model_config = ConfigDict(frozen=True)

    gb_per_rank: float = 34.9 / 1024
    gb_per_replay_spike_per_rank: float = 41.4 / 2**30
    gb_per_rank_with_lfp: float = 6.5 / 1024
    gb_per_cell: float = 5.55 / 1024
    gb_per_synapse: float = 3.07 / 2**20
    gb_per_replayed_synapse: float = 2.05 / 2**20
    lfp_weights_factor: float = 1.04
    margin: float = 1.15
    usable_fraction: float = 0.9
    min_gb_per_cell: float = 0.03
    # For the simulations whose synapses were not counted.
    uncounted_gb_per_cell: float = 0.09

    def per_node_gb(self, ranks: int, spikes: int, *, lfp: bool) -> float:
        """The memory every node holds, whatever the number of nodes."""
        per_rank = self.gb_per_rank + self.gb_per_replay_spike_per_rank * spikes
        if lfp:
            per_rank += self.gb_per_rank_with_lfp
        return self.margin * ranks * per_rank

    def split_gb(self, cells: int, synapses: int, replayed: int, lfp_weights_gb: float) -> float:
        """The memory split over the nodes."""
        return self.margin * (
            self.gb_per_cell * cells
            + self.gb_per_synapse * synapses
            + self.gb_per_replayed_synapse * replayed
            + self.lfp_weights_factor * lfp_weights_gb
        )


MEMORY_MODEL = MemoryModel()


def lfp_weights_gb(config: models.Simulation, db_client: Client) -> float:
    """The LFP weights of the simulated cells, estimated from the weight matrices."""
    if not config.recording_arrays:
        return 0.0
    circuit = db_client.get_entity(entity_id=config.entity_id, entity_type=models.Circuit)
    share = min(1.0, SUBSET_FACTOR * config.number_neurons / max(circuit.number_neurons, 1))
    weights = 0
    for linked in config.recording_arrays:
        array = db_client.get_entity(
            entity_id=linked.id, entity_type=models.SimulatableExtracellularRecordingArray
        )
        weights += sum(
            a.size or 0 for a in array.assets if a.label == AssetLabel.electrode_array_weight_matrix
        )
    return share * weights / 2**30


def nodes_per_cell(gb_per_cell: float, cells: int, instance: ClusterInstanceInfo) -> int:
    return math.ceil(gb_per_cell * cells / instance.memory_per_instance_gb)


def simulation_nodes(
    config: models.Simulation,
    instance: ClusterInstanceInfo,
    db_client: Client,
    model: MemoryModel = MEMORY_MODEL,
) -> int:
    """The nodes a simulation needs."""
    cells = config.number_neurons
    # 0: not counted (generated before the counts existed).
    synapses = getattr(config, "number_synapses", 0)
    if not synapses:
        return nodes_per_cell(model.uncounted_gb_per_cell, cells, instance)
    spikes = getattr(config, "number_replay_spikes", 0)
    replayed = getattr(config, "number_replayed_synapses", 0)

    per_node = model.per_node_gb(
        instance.ranks_per_instance, spikes, lfp=bool(config.recording_arrays)
    )
    split = model.split_gb(cells, synapses, replayed, lfp_weights_gb(config, db_client))
    room = model.usable_fraction * instance.memory_per_instance_gb - per_node
    if room <= 0:
        raise ApiError(
            message=(
                f"The spike inputs of the simulation hold {spikes:,} spikes. Every one of the "
                f"{instance.ranks_per_instance} processes of a node reads them all, which needs "
                f"{per_node:,.0f} GB of the {instance.memory_per_instance_gb} GB of a node, "
                "however many nodes run it. Lower the rate, the duration or the sources of the "
                "spike stimuli."
            ),
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
        )
    nodes = max(1, math.ceil(split / room), nodes_per_cell(model.min_gb_per_cell, cells, instance))
    if instance.max_instances is not None and nodes > instance.max_instances:
        raise ApiError(
            message=(
                f"The simulation needs {nodes} nodes of {instance.memory_per_instance_gb} GB for "
                f"its {cells:,} neurons and {synapses:,} synapses, and at most "
                f"{instance.max_instances} are available. Simulate fewer neurons, or replay fewer "
                "sources."
            ),
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
        )
    return nodes


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
    n_nodes = simulation_nodes(config, instance, db_client)
    instance_type = instance.name

    return task_definition.resources.model_copy(
        update={
            "instances": n_nodes,
            "instance_type": instance_type,
            "compute_cell": compute_cell,
        }
    )  # ty:ignore[invalid-return-type]
