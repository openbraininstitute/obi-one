from typing import Annotated, Literal
from uuid import UUID

from entitysdk.models.activity import Activity, Entity
from entitysdk.types import AssetLabel
from obp_accounting_sdk.constants import ServiceSubtype
from pydantic import Field

from app.schemas.accounting import AccountingParameters
from app.schemas.base import Schema
from app.types import (
    BuiltinScript,
    CodeType,
    ResourcesConfigType,
    TaskType,
)


class PythonRepositoryCode(Schema):
    type: Literal[CodeType.python_repository] = CodeType.python_repository
    location: str
    ref: str
    path: str
    dependencies: str


class BuiltinCode(Schema):
    type: Literal[CodeType.builtin] = CodeType.builtin
    script: BuiltinScript


Code = Annotated[
    PythonRepositoryCode | BuiltinCode,
    Field(discriminator="type"),
]


class MachineResources(Schema):
    """MachineResources schema to be used when reading existing jobs."""

    type: Literal[ResourcesConfigType.machine] = ResourcesConfigType.machine
    cores: int = 1
    memory: int = 2
    timelimit: str | None = None


class ClusterResources(Schema):
    """ClusterResources schema to be used when reading existing jobs."""

    type: Literal[ResourcesConfigType.cluster] = ResourcesConfigType.cluster
    instances: int
    instance_type: str
    timelimit: str | None = None


Resources = Annotated[
    MachineResources | ClusterResources,
    Field(discriminator="type"),
]


class TaskLaunchSubmit(Schema):
    """Request model for task launch."""

    task_type: TaskType
    config_id: UUID


class TaskLaunchInfo(TaskLaunchSubmit):
    activity_id: UUID
    job_id: UUID


class TaskAccountingCreate(Schema):
    """Request model for task cost estimate."""

    task_type: TaskType
    config_id: UUID


class TaskAccountingInfo(TaskAccountingCreate):
    cost: float
    parameters: AccountingParameters


class TaskDefinition(Schema):
    """Definition of a task type with its associated models and configuration."""

    task_type: TaskType
    config_type: type[Entity]
    activity_type: type[Activity]
    accounting_service_subtype: ServiceSubtype
    config_asset_label: AssetLabel
    code: Code
    resources: Resources

    @property
    def config_type_name(self) -> str:
        """Return the name of the config class."""
        return self.config_type.__name__

    @property
    def activity_type_name(self) -> str:
        """Return the name of the activity class."""
        return self.activity_type.__name__


class TaskCallBackSuccessRequest(Schema):
    task_type: TaskType
    job_id: UUID
    count: int
