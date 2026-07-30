"""Registries for task dispatch and block reference lookup.

Scientific modules populate these registries at import time.
Core modules consume them at runtime.

Registries:
    - TaskRegistry: maps config classes to task classes, and TaskType enums
      to task classes, single configs, asset labels, and the entitycore
      TaskConfig/TaskActivity types used to register campaigns and single configs.
    - BlockReferenceRegistry: maps BlockReference subclass names to their
      classes for use in ScanConfig.add().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

    from obi_one.types import TaskType


@dataclass(frozen=True)
class TaskRegistration:
    """Everything the framework needs to dispatch and register one task type.

    The `*_task_config_type` and `*_task_activity_type` fields name the entitycore
    entities created when a campaign or a single config is registered. They are
    None for tasks that are not registered against the database.
    """

    task_cls: type
    single_config_cls: type
    scan_config_cls: type | None = None
    asset_label: AssetLabel | None = None
    campaign_task_config_type: TaskConfigType | None = None
    campaign_generation_task_activity_type: TaskActivityType | None = None
    single_task_config_type: TaskConfigType | None = None
    single_task_activity_type: TaskActivityType | None = None


class TaskRegistry:
    """Maps config classes and TaskType enums to their TaskRegistration."""

    def __init__(self) -> None:
        """Initialize empty registry maps."""
        self._task_type_map: dict[TaskType, TaskRegistration] = {}
        # Both the ScanConfig and the SingleConfig class point at their registration,
        # so either end of a task can look up the types it needs to register itself.
        self._by_config_cls: dict[type, TaskRegistration] = {}

    def register_task(self, task_type: TaskType, registration: TaskRegistration) -> None:
        """Register a task with all its associated mappings in one call."""
        self._task_type_map[task_type] = registration
        self._by_config_cls[registration.single_config_cls] = registration
        if registration.scan_config_cls is not None:
            self._by_config_cls[registration.scan_config_cls] = registration

    def get_registration_for_config(self, config_cls: type) -> TaskRegistration | None:
        """Return the registration for a config class, or None if it has none.

        Walks the MRO so a subclass resolves the registration of the config it
        derives from, matching the inheritance the config types used to rely on.
        """
        for klass in config_cls.__mro__:
            registration = self._by_config_cls.get(klass)
            if registration is not None:
                return registration
        return None

    def get_configs_task_type(self, config: object) -> type:
        """Return the Task class for a given config instance."""
        registration = self._by_config_cls.get(config.__class__)
        if registration is None:
            msg = f"No task registered for config class '{config.__class__.__name__}'."
            raise KeyError(msg)
        return registration.task_cls

    def get_task_type(self, task_type: TaskType) -> type:
        """Return the Task class for a given TaskType enum."""
        return self._task_type_map[task_type].task_cls

    def get_task_type_single_config(self, task_type: TaskType) -> type:
        """Return the SingleConfig class for a given TaskType enum."""
        return self._task_type_map[task_type].single_config_cls

    def get_task_type_config_asset_label(self, task_type: TaskType) -> AssetLabel | None:
        """Return the config asset label for a given TaskType enum.

        Returns None if the task type does not use a config asset (e.g., tasks that receive their
        config inline rather than as a stored asset).
        """
        registration = self._task_type_map.get(task_type)
        return registration.asset_label if registration is not None else None


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
