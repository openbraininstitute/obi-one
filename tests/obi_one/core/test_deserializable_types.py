import pytest

from obi_one.core.deserializable_types import TYPE_MAP, load_class


@pytest.mark.parametrize("type_name", TYPE_MAP.keys())
def test_type_map_entry_resolves(type_name):
    """Every entry in TYPE_MAP must resolve to a class with model_validate."""
    cls = load_class(type_name)
    assert cls is not None
    assert hasattr(cls, "model_validate")
