"""Task specs and block reference lookup.

Task dispatch maps live in ``config_task_map`` (lazy resolve + cache).
Block references are registered at import time via ``block_ref_registry``.
"""

from dataclasses import dataclass

from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

from obi_one.core.base import OBIBaseModel


@dataclass(frozen=True)
class TaskSpec:
    """Everything the framework needs to dispatch and register one task type.

    The `*_task_config_type` and `*_task_activity_type` fields name the entitycore
    entities created when a campaign or a single config is registered. They are
    None for tasks that are not registered against the database.
    """

    task_cls: type
    single_config_cls: type[OBIBaseModel]
    scan_config_cls: type[OBIBaseModel] | None = None
    asset_label: AssetLabel | None = None
    campaign_task_config_type: TaskConfigType | None = None
    campaign_generation_task_activity_type: TaskActivityType | None = None
    single_task_config_type: TaskConfigType | None = None
    single_task_activity_type: TaskActivityType | None = None


class BlockReferenceRegistry:
    """Maps BlockReference subclass names to their classes.

    Used by ScanConfig.add() to resolve a reference type by name
    when adding a block to a scan configuration.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._by_name: dict[str, type] = {}

    def register(self, cls: type) -> None:
        """Register a BlockReference subclass."""
        self._by_name[cls.__name__] = cls

    def get_by_name(self, name: str) -> type | None:
        """Return the BlockReference subclass with the given name, or None."""
        return self._by_name.get(name)


# Module-level singleton
block_ref_registry = BlockReferenceRegistry()
