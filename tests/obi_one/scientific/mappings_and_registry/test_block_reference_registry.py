"""Tests that ``BLOCK_REFERENCE_SPECS`` declares valid, importable block reference classes."""

import pytest

from obi_one.core.block_reference import BlockReference
from obi_one.core.registry import block_ref_registry
from obi_one.scientific.mappings_and_registry.block_reference_registry import (
    BLOCK_REFERENCE_SPECS,
)
from obi_one.utils.lazy_import import class_name, import_class

DECLARED_BLOCK_REFERENCE_REFS = tuple(BLOCK_REFERENCE_SPECS.items())


@pytest.mark.parametrize(
    ("ref_name", "class_ref"),
    DECLARED_BLOCK_REFERENCE_REFS,
    ids=[name for name, _ in DECLARED_BLOCK_REFERENCE_REFS],
)
def test_declared_block_reference_class_ref_is_importable(ref_name, class_ref):
    """Every entry in ``BLOCK_REFERENCE_SPECS`` must import a ``BlockReference`` subclass."""
    assert ref_name == class_name(class_ref), (
        f"Spec key {ref_name!r} must match class name {class_name(class_ref)!r}"
    )

    cls = import_class(class_ref)

    assert isinstance(cls, type), f"{class_ref} is not a class"
    assert cls.__qualname__ == class_name(class_ref), (
        f"{class_ref} resolves to {cls.__qualname__!r}, not {class_name(class_ref)!r}"
    )
    assert issubclass(cls, BlockReference), f"{cls.__qualname__} is not a BlockReference"


_BLOCK_REFERENCE_NAMES = list(BLOCK_REFERENCE_SPECS)


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
