import pytest
from pydantic import ValidationError

from obi_one.core.base import OBIBaseModel
from obi_one.core.tuple import NamedTuple


class TestNamedTuple:
    def test_creation(self):
        nt = NamedTuple(name="my_tuple", elements=(1, 2, 3))
        assert nt.name == "my_tuple"
        assert nt.elements == (1, 2, 3)

    def test_default_name(self):
        nt = NamedTuple(elements=(0,))
        assert nt.name == "Default name"

    def test_repr_returns_name(self):
        nt = NamedTuple(name="test_tuple", elements=(5, 10))
        assert repr(nt) == "test_tuple"

    def test_str_returns_repr(self):
        nt = NamedTuple(name="output", elements=(0, 1))
        assert str(nt) == repr(nt)

    def test_is_obi_base_model(self):
        assert issubclass(NamedTuple, OBIBaseModel)

    def test_negative_element_raises(self):
        with pytest.raises(ValidationError):
            NamedTuple(elements=(-1, 0, 1))

    def test_empty_tuple(self):
        nt = NamedTuple(elements=())
        assert nt.elements == ()

    def test_single_element(self):
        nt = NamedTuple(elements=(42,))
        assert nt.elements == (42,)

    def test_serialization_round_trip(self):
        nt = NamedTuple(name="test", elements=(1, 2, 3))
        dump = nt.model_dump()
        restored = NamedTuple.model_validate(dump)
        assert restored.name == nt.name
        assert restored.elements == nt.elements
