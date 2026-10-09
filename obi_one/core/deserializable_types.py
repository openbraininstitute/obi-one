"""Mapping of serialized ``type`` values to the classes that implement them.

Used by core/deserialize.py to resolve the concrete class for a given 'type' field in
serialized JSON without importing all scientific modules eagerly.

Task config classes are not listed here: they are derived from the ``TaskSpec`` references
in ``config_task_map``, so registering a task type also makes its configs deserializable.
Only framework classes and ``__init__``/alias re-exports, which no task spec declares,
are listed explicitly.
"""

from obi_one.core.registry import TaskSpec
from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.types import TaskType
from obi_one.utils.lazy_import import ClassRef, class_name, import_class

SIMULATION_ALIASES = "obi_one.scientific.tasks.generate_simulations.config.neuron.aliases"

CORE_TYPE_REFS: tuple[ClassRef, ...] = (
    ("obi_one.core.block", "Block"),
    ("obi_one.core.block_reference", "BlockReference"),
    ("obi_one.core.scan_generation", "CoupledScanGenerationTask"),
    ("obi_one.core.scan_generation", "GridScanGenerationTask"),
    ("obi_one.core.info", "Info"),
    ("obi_one.core.path", "NamedPath"),
    ("obi_one.core.tuple", "NamedTuple"),
    ("obi_one.core.scan_config", "ScanConfig"),
)

ALIAS_TYPE_REFS: tuple[ClassRef, ...] = (
    ("obi_one", "CoupledScan"),
    ("obi_one", "GridScan"),
    (SIMULATION_ALIASES, "Simulation"),
    (SIMULATION_ALIASES, "SimulationsForm"),
)


def build_type_map(
    core_type_refs: tuple[ClassRef, ...] = CORE_TYPE_REFS,
    alias_type_refs: tuple[ClassRef, ...] = ALIAS_TYPE_REFS,
    task_specs: dict[TaskType, TaskSpec] = TASK_SPECS,
) -> dict[str, ClassRef]:
    """Index every deserializable class reference by the ``type`` value it is stored under."""
    refs = [
        *core_type_refs,
        *alias_type_refs,
        *(ref for task_spec in task_specs.values() for ref in task_spec.config_refs),
    ]
    type_map: dict[str, ClassRef] = {}
    for ref in refs:
        name = class_name(ref)
        existing = type_map.get(name)
        if existing is not None and existing != ref:
            msg = f"Duplicate deserializable type {name!r}: {existing!r} and {ref!r}"
            raise ValueError(msg)
        type_map[name] = ref
    return type_map


TYPE_MAP: dict[str, ClassRef] = build_type_map()


def load_class(type_name: str) -> type:
    """Resolve a type name to its class using TYPE_MAP and lazy import."""
    return import_class(TYPE_MAP[type_name])
