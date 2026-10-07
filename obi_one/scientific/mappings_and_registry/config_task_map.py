"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.mappings_and_registry.config_task_map import (
    AssetLabel,
    get_single_configs_task_type,
    get_task_type,
    get_task_type_config_asset_label,
    get_task_type_single_config,
    register_all_tasks,
    resolve_task_registration,
    TASK_MAP,
    task_registry,
    TaskActivityType,
    TaskConfigType,
    TaskRegistration,
    TaskType,
)

from obi_one_lazy.scientific.mappings_and_registry.config_task_map import (
    _CACHE,
)

__all__ = [
    "AssetLabel",
    "get_single_configs_task_type",
    "get_task_type",
    "get_task_type_config_asset_label",
    "get_task_type_single_config",
    "register_all_tasks",
    "resolve_task_registration",
    "TASK_MAP",
    "task_registry",
    "TaskActivityType",
    "TaskConfigType",
    "TaskRegistration",
    "TaskType",
    "_CACHE",
]
