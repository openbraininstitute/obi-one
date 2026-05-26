"""Registries for task dispatch and block reference lookup.

Scientific modules populate these registries at import time.
Core modules consume them at runtime.

Registries:
    - TaskRegistry: maps config classes to task classes, and TaskType enums
      to task classes, single configs, and asset labels.
    - BlockReferenceRegistry: maps BlockReference subclass names to their
      classes for use in ScanConfig.add().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entitysdk.types import AssetLabel

    from obi_one.types import TaskType


class TaskRegistry:
    """Maps config classes to task classes, and TaskType enums to task/config/label."""

    def __init__(self) -> None:
        """Initialize empty registry maps."""
        # SingleConfig class -> Task class (used to dispatch execution)
        self._config_task_map: dict[type, type] = {}
        # TaskType -> (Task class, SingleConfig class, AssetLabel | None)
        self._task_type_map: dict[TaskType, tuple[type, type, AssetLabel | None]] = {}

    def register_task(
        self,
        *,
        task_type: TaskType,
        task_cls: type,
        single_config_cls: type,
        asset_label: AssetLabel | None = None,
    ) -> None:
        """Register a task with all its associated mappings in one call."""
        self._config_task_map[single_config_cls] = task_cls
        self._task_type_map[task_type] = (task_cls, single_config_cls, asset_label)

    def get_configs_task_type(self, config: object) -> type:
        """Return the Task class for a given config instance."""
        return self._config_task_map[config.__class__]

    def get_task_type(self, task_type: TaskType) -> type:
        """Return the Task class for a given TaskType enum."""
        return self._task_type_map[task_type][0]

    def get_task_type_single_config(self, task_type: TaskType) -> type:
        """Return the SingleConfig class for a given TaskType enum."""
        return self._task_type_map[task_type][1]

    def get_task_type_config_asset_label(self, task_type: TaskType) -> AssetLabel | None:
        """Return the config asset label for a given TaskType enum.

        Returns None if the task type does not use a config asset (e.g., tasks that receive their
        config inline rather than as a stored asset).
        """
        entry = self._task_type_map.get(task_type)
        return entry[2] if entry is not None else None


# Module-level singleton
task_registry = TaskRegistry()


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
