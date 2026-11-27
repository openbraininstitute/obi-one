from app.schemas.base import Schema


class ClusterInstanceInfo(Schema):
    name: str
    memory_per_instance_gb: int
    max_neurons: int
    ranks_per_instance: int
    max_instances: int | None = None
