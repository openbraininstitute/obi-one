import sys

import pytest

from obi_one.core.block import Block
from obi_one.utils.lazy_import import class_name, import_class, import_optional, module_name

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


def test_import_optional_returns_the_module():
    assert import_optional("json", extra="any") is sys.modules["json"]


def test_import_optional_missing_names_package_and_extra(monkeypatch):
    # A None entry in sys.modules makes `import` raise ImportError.
    monkeypatch.setitem(sys.modules, "somepkg", None)
    with pytest.raises(ImportError, match=r"'somepkg'.*'obi-one\[someextra\]'") as exc_info:
        import_optional("somepkg.sub", extra="someextra")
    assert isinstance(exc_info.value.__cause__, ImportError)
