"""Task spec declarations for ``config_task_map``.

Task dispatch maps live in ``config_task_map`` (declarative, resolved on use).
Block reference lookup lives in ``scientific.mappings_and_registry.block_reference_registry``.
"""

from dataclasses import dataclass

from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

from obi_one.core.base import OBIBaseModel
from obi_one.utils.lazy_import import ClassRef, import_class


def _import_config_class(class_ref: ClassRef) -> type[OBIBaseModel]:
    """Import a config class by reference, rejecting refs that do not name an OBIBaseModel."""
    cls = import_class(class_ref)
    if not issubclass(cls, OBIBaseModel):
        msg = f"{class_ref!r} does not name an OBIBaseModel subclass"
        raise TypeError(msg)
    return cls


@dataclass(frozen=True, eq=False, order=False)
class TaskSpec:
    """Everything the framework needs to dispatch and register one task type.

    Classes are declared as ``(module path, class name)`` references and imported by the
    ``*_cls`` properties on first access, so holding a spec costs no task imports.

    The `*_task_config_type` and `*_task_activity_type` fields name the entitycore
    entities created when a campaign or a single config is registered. They are
    None for tasks that are not registered against the database.

    ``requires_package`` names an optional dependency the task needs; task types whose
    dependency is missing are reported as unavailable instead of failing on import.
    """

    task_ref: ClassRef
    single_config_ref: ClassRef
    scan_config_ref: ClassRef | None = None
    asset_label: AssetLabel | None = None
    campaign_task_config_type: TaskConfigType | None = None
    campaign_generation_task_activity_type: TaskActivityType | None = None
    single_task_config_type: TaskConfigType | None = None
    single_task_activity_type: TaskActivityType | None = None
    requires_package: str | None = None

    @property
    def task_cls(self) -> type:
        """The task class, imported on first access."""
        return import_class(self.task_ref)

    @property
    def single_config_cls(self) -> type[OBIBaseModel]:
        """The SingleConfig class, imported on first access."""
        return _import_config_class(self.single_config_ref)

    @property
    def scan_config_cls(self) -> type[OBIBaseModel] | None:
        """The ScanConfig class, imported on first access, or None if the task has none."""
        if self.scan_config_ref is None:
            return None
        return _import_config_class(self.scan_config_ref)

    @property
    def config_refs(self) -> tuple[ClassRef, ...]:
        """The deserializable config class references declared by this spec."""
        if self.scan_config_ref is None:
            return (self.single_config_ref,)
        return (self.single_config_ref, self.scan_config_ref)
