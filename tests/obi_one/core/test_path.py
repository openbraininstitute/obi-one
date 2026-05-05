from obi_one.core.base import OBIBaseModel
from obi_one.core.path import NamedPath


class TestNamedPath:
    def test_creation(self):
        np = NamedPath(name="my_file", path="/data/test.txt")
        assert np.name == "my_file"
        assert np.path == "/data/test.txt"

    def test_repr_returns_name(self):
        np = NamedPath(name="circuit_config", path="/data/circuit.json")
        assert repr(np) == "circuit_config"

    def test_str_returns_repr(self):
        np = NamedPath(name="output", path="/results/output.h5")
        assert str(np) == repr(np)

    def test_is_obi_base_model(self):
        assert issubclass(NamedPath, OBIBaseModel)

    def test_type_field(self):
        np = NamedPath(name="a", path="b")
        assert np.type == "NamedPath"

    def test_serialization_round_trip(self):
        np = NamedPath(name="test", path="/some/path")
        dump = np.model_dump()
        restored = NamedPath.model_validate(dump)
        assert restored.name == np.name
        assert restored.path == np.path
