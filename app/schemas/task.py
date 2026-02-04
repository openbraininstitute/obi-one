from uuid import UUID

from entitysdk.models.activity import Activity, Entity
from entitysdk.types import AssetLabel
from obp_accounting_sdk.constants import ServiceSubtype

from app.schemas.accounting import AccountingParameters
from app.schemas.base import Schema
from app.types import TaskType


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
    code: dict
    resources: dict

    @property
    def config_type_name(self) -> str:
        """Return the name of the config class."""
        return self.config_type.__name__

    @property
    def activity_type_name(self) -> str:
        """Return the name of the activity class."""
        return self.activity_type.__name__
