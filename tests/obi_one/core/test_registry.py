import pytest

from obi_one.core.block import Block
from obi_one.core.registry import _import_config_class


def test_import_config_class_resolves_an_obibasemodel():
    assert _import_config_class(("obi_one.core.block", "Block")) is Block


def test_import_config_class_rejects_a_non_config_class():
    with pytest.raises(TypeError, match="does not name an OBIBaseModel subclass"):
        _import_config_class(("obi_one.core.registry", "BlockReferenceRegistry"))
