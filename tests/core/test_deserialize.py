"""Tests for obi_one.core.deserialize functions."""

import json

from obi_one.core.deserialize import (
    deserialize_obi_object_from_json_data,
    deserialize_obi_object_from_json_file,
)
from obi_one.core.path import NamedPath


def make_named_path_dict():
    """Create a serialized NamedPath dict (a simple OBIBaseModel)."""
    obj = NamedPath(name="test_path", path="/data/test")
    return json.loads(obj.model_dump_json())


class TestDeserializeObiObjectFromJsonData:
    def test_deserializes_named_path(self):
        data = make_named_path_dict()
        obj = deserialize_obi_object_from_json_data(data)
        assert isinstance(obj, NamedPath)
        assert obj.name == "test_path"
        assert obj.path == "/data/test"

    def test_preserves_type_field(self):
        data = make_named_path_dict()
        obj = deserialize_obi_object_from_json_data(data)
        assert obj.type == "NamedPath"

    def test_round_trip(self):
        original = NamedPath(name="round_trip", path="/data/file.h5")
        data = json.loads(original.model_dump_json())
        restored = deserialize_obi_object_from_json_data(data)
        assert restored.name == original.name
        assert restored.path == original.path


class TestDeserializeObiObjectFromJsonFile:
    def test_deserializes_from_file(self, tmp_path):
        data = make_named_path_dict()
        json_path = tmp_path / "obj.json"
        json_path.write_text(json.dumps(data))

        obj = deserialize_obi_object_from_json_file(json_path)
        assert isinstance(obj, NamedPath)
        assert obj.name == "test_path"

    def test_round_trip_from_file(self, tmp_path):
        original = NamedPath(name="file_test", path="/some/path")
        data = json.loads(original.model_dump_json())
        json_path = tmp_path / "round_trip.json"
        json_path.write_text(json.dumps(data))

        restored = deserialize_obi_object_from_json_file(json_path)
        assert restored.name == original.name
