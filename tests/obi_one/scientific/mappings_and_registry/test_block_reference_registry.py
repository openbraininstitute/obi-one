"""Tests that block reference specs declare valid, importable block reference classes."""

import pytest

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.mappings_and_registry.block_reference_registry import (
    _BLOCK_REFERENCE_SPECS,
    BlockReferenceRegistry,
    block_ref_registry,
)
from obi_one.utils.lazy_import import class_name, import_class

DECLARED_BLOCK_REFERENCE_REFS = tuple(_BLOCK_REFERENCE_SPECS.items())


@pytest.mark.parametrize(
    ("ref_name", "class_ref"),
    DECLARED_BLOCK_REFERENCE_REFS,
    ids=[name for name, _ in DECLARED_BLOCK_REFERENCE_REFS],
)
def test_declared_block_reference_class_ref_is_importable(ref_name, class_ref):
    """Every declared block reference spec must import a ``BlockReference`` subclass."""
    assert ref_name == class_name(class_ref), (
        f"Spec key {ref_name!r} must match class name {class_name(class_ref)!r}"
    )

    cls = import_class(class_ref)

    assert isinstance(cls, type), f"{class_ref} is not a class"
    assert cls.__qualname__ == class_name(class_ref), (
        f"{class_ref} resolves to {cls.__qualname__!r}, not {class_name(class_ref)!r}"
    )
    assert issubclass(cls, BlockReference), f"{cls.__qualname__} is not a BlockReference"


_BLOCK_REFERENCE_NAMES = list(_BLOCK_REFERENCE_SPECS)


@pytest.mark.parametrize(
    "ref_name",
    _BLOCK_REFERENCE_NAMES,
    ids=_BLOCK_REFERENCE_NAMES,
)
def test_block_ref_registry_get_by_name_resolves_spec(ref_name):
    """``block_ref_registry`` must resolve each declared reference by name."""
    cls = block_ref_registry.get_by_name(ref_name)
    assert cls is not None, f"No registry entry for {ref_name!r}"
    assert cls.__name__ == ref_name
    assert issubclass(cls, BlockReference)


def test_block_ref_registry_get_by_name_returns_none_for_unknown():
    registry = BlockReferenceRegistry()
    assert registry.get_by_name("NotARealBlockReferenceName") is None


def test_block_ref_registry_get_by_name_caches_resolved_class():
    registry = BlockReferenceRegistry()
    first = registry.get_by_name("StimulusReference")
    second = registry.get_by_name("StimulusReference")
    assert first is not None
    assert first is second
