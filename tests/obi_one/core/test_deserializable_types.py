import pytest

from obi_one.core.deserializable_types import (
    _ALIAS_TYPE_REFS,
    _CORE_TYPE_REFS,
    TYPE_MAP,
    _build_type_map,
    load_class,
)
from obi_one.scientific.mappings_and_registry.config_task_map import (
    TASK_SPECS,
    _is_task_type_available,
)
from obi_one.utils.lazy_import import class_name


@pytest.mark.parametrize("type_name", TYPE_MAP.keys())
def test_type_map_entry_resolves(type_name):
    """Every entry in TYPE_MAP must resolve to a class with model_validate."""
    task_types = [
        task_type
        for task_type, task_spec in TASK_SPECS.items()
        if TYPE_MAP[type_name] in task_spec.config_refs
    ]
    if task_types and not any(_is_task_type_available(task_type) for task_type in task_types):
        pytest.skip(f"{type_name} requires an optional dependency that is not installed")

    cls = load_class(type_name)

    assert cls is not None
    assert hasattr(cls, "model_validate")
    assert cls.__qualname__ == type_name


def test_type_map_keys_are_the_class_names_of_their_refs():
    assert all(class_name(ref) == type_name for type_name, ref in TYPE_MAP.items())


@pytest.mark.parametrize("task_type", list(TASK_SPECS))
def test_every_task_config_class_is_deserializable(task_type):
    """Registering a task type must make its configs deserializable, with no extra bookkeeping."""
    task_spec = TASK_SPECS[task_type]

    for ref in task_spec.config_refs:
        assert TYPE_MAP[class_name(ref)] == ref


def test_type_map_covers_core_and_alias_refs():
    declared = {class_name(ref): ref for ref in (*_CORE_TYPE_REFS, *_ALIAS_TYPE_REFS)}

    assert declared.items() <= TYPE_MAP.items()


def test_build_type_map_rejects_duplicate_type_names():
    with pytest.raises(ValueError, match="Duplicate deserializable type 'Block'"):
        _build_type_map(
            core_type_refs=(
                ("obi_one.core.block", "Block"),
                ("obi_one.core.other", "Block"),
            ),
            alias_type_refs=(),
            task_specs={},
        )
