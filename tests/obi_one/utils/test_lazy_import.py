import pytest

from obi_one.core.block import Block
from obi_one.utils.lazy_import import class_name, import_class, module_name

BLOCK_REF = ("obi_one.core.block", "Block")


def test_import_class_resolves_the_reference():
    assert import_class(BLOCK_REF) is Block


def test_import_class_is_cached():
    assert import_class(BLOCK_REF) is import_class(BLOCK_REF)


def test_import_class_rejects_a_malformed_reference():
    with pytest.raises(ValueError, match="unpack"):
        import_class(("obi_one.core.block",))


def test_import_class_unknown_module_raises():
    with pytest.raises(ModuleNotFoundError):
        import_class(("obi_one.core.does_not_exist", "Block"))


def test_import_class_unknown_name_raises():
    with pytest.raises(AttributeError):
        import_class(("obi_one.core.block", "DoesNotExist"))


def test_class_name_and_module_name_do_not_import():
    assert class_name(BLOCK_REF) == "Block"
    assert module_name(BLOCK_REF) == "obi_one.core.block"
