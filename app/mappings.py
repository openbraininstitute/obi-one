from entitysdk import models
from entitysdk.types import AssetLabel
from obp_accounting_sdk.constants import ServiceSubtype

from app.schemas.task import TaskDefinition
from app.types import TaskType

TASK_DEFINITIONS: dict[TaskType, TaskDefinition] = {
    TaskType.circuit_extraction: TaskDefinition(
        task_type=TaskType.circuit_extraction,
        config_type=models.CircuitExtractionConfig,
        activity_type=models.CircuitExtractionExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_CIRCUIT_SIM,
        config_asset_label=AssetLabel.circuit_extraction_config,
    ),
    TaskType.circuit_simulation: TaskDefinition(
        task_type=TaskType.circuit_simulation,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,  # May be overridden by circuit scale
        config_asset_label=AssetLabel.sonata_simulation_config,
    ),
}
