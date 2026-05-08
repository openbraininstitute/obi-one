"""Registries for task dispatch and type resolution.

Scientific modules populate these registries at import time.
Core modules consume them at runtime to look up task classes, config mappings,
and type information.
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
        # TaskType -> Task class (used for run_task_type entrypoint)
        self._task_type_task_map: dict[TaskType, type] = {}
        # TaskType -> SingleConfig class (used to create default configs)
        self._task_type_single_config_map: dict[TaskType, type] = {}
        # TaskType -> AssetLabel or None (used to locate config assets)
        self._task_type_config_asset_label_map: dict[TaskType, AssetLabel | None] = {}

    def register_config_task(self, config_cls: type, task_cls: type) -> None:
        """Register a config class to task class mapping."""
        self._config_task_map[config_cls] = task_cls

    def register_task_type(self, task_type: TaskType, task_cls: type) -> None:
        """Register a TaskType to task class mapping."""
        self._task_type_task_map[task_type] = task_cls

    def register_task_type_single_config(self, task_type: TaskType, config_cls: type) -> None:
        """Register a TaskType to single config class mapping."""
        self._task_type_single_config_map[task_type] = config_cls

    def register_task_type_config_asset_label(
        self, task_type: TaskType, label: AssetLabel | None
    ) -> None:
        """Register a TaskType to config asset label mapping."""
        self._task_type_config_asset_label_map[task_type] = label

    def get_configs_task_type(self, config: object) -> type:
        """Return the Task class for a given config instance."""
        return self._config_task_map[config.__class__]

    def get_task_type(self, task_type: TaskType) -> type:
        """Return the Task class for a given TaskType enum."""
        return self._task_type_task_map[task_type]

    def get_task_type_single_config(self, task_type: TaskType) -> type:
        """Return the SingleConfig class for a given TaskType enum."""
        return self._task_type_single_config_map[task_type]

    def get_task_type_config_asset_label(self, task_type: TaskType) -> AssetLabel | None:
        """Return the config asset label for a given TaskType enum.

        Returns None if the task type does not use a config asset (e.g., tasks that receive their
        config inline rather than as a stored asset).
        """
        return self._task_type_config_asset_label_map.get(task_type)


# Module-level singleton
task_registry = TaskRegistry()
