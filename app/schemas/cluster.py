from app.schemas.base import Schema


class ClusterInstanceInfo(Schema):
    name: str
    memory_per_instance_gb: int
    max_neurons: int
    # MPI ranks a node runs: launch-system starts one per core (`nproc --all`).
    ranks_per_instance: int
    # The most nodes of this type a job can get, None if not known. A request for more never runs.
    max_instances: int | None = None
