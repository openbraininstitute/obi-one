from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel, ValidationError

from obi_one.core.base import OBIBaseModel


class SimpleModel(OBIBaseModel):
    value: int = 0


class TitledModel(OBIBaseModel):
    title: ClassVar[str] = "Custom Title"
    value: str = ""


class ModelWithExtraAdditions(OBIBaseModel):
    json_schema_extra_additions: ClassVar[dict] = {"ui_enabled": True, "category": "test"}
    value: float = 1.0


class ChildModel(SimpleModel):
    extra_value: str = "child"


class TestOBIBaseModelTypeField:
    def test_type_field_is_set_on_instance(self):
        obj = SimpleModel()
        assert obj.type == "SimpleModel"

    def test_type_annotation_is_literal(self):
        assert SimpleModel.__annotations__["type"] is Literal["SimpleModel"]

    def test_type_field_set_from_dict(self):
        obj = SimpleModel.model_validate({"value": 42})
        assert obj.type == "SimpleModel"

    def test_type_field_not_overwritten_when_provided(self):
        obj = SimpleModel.model_validate({"type": "SimpleModel", "value": 10})
        assert obj.type == "SimpleModel"
        assert obj.value == 10

    def test_type_set_from_dict_via_model_validator(self):
        data = {"value": 5}
        assert "type" not in data
        obj = SimpleModel.model_validate(data)
        assert obj.type == "SimpleModel"

    def test_type_field_on_child_instance(self):
        obj = ChildModel()
        assert obj.type == "ChildModel"

    def test_child_type_different_from_parent(self):
        parent = SimpleModel()
        child = ChildModel()
        assert parent.type != child.type

    def test_instantiation_without_dict(self):
        obj = SimpleModel(value=99)
        assert obj.type == "SimpleModel"
        assert obj.value == 99


class TestOBIBaseModelConfig:
    def test_discriminator_is_type(self):
        assert SimpleModel.model_config.get("discriminator") == "type"

    def test_extra_is_forbid(self):
        assert SimpleModel.model_config.get("extra") == "forbid"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            SimpleModel(value=1, unknown_field="bad")

    def test_json_schema_extra_is_dict(self):
        assert isinstance(SimpleModel.model_config.get("json_schema_extra"), dict)


class TestOBIBaseModelTitle:
    def test_default_title_is_class_name(self):
        assert SimpleModel.model_config.get("title") == "SimpleModel"

    def test_custom_title(self):
        assert TitledModel.model_config.get("title") == "Custom Title"


class TestOBIBaseModelJsonSchemaExtraAdditions:
    def test_additions_propagated_to_config(self):
        schema_extra = ModelWithExtraAdditions.model_config.get("json_schema_extra")
        assert schema_extra["ui_enabled"] is True
        assert schema_extra["category"] == "test"

    def test_additions_do_not_leak_to_sibling(self):
        schema_extra = SimpleModel.model_config.get("json_schema_extra")
        assert "ui_enabled" not in schema_extra
        assert "category" not in schema_extra


class TestOBIBaseModelConfigIsolation:
    def test_model_config_deep_copied_per_subclass(self):
        assert SimpleModel.model_config is not TitledModel.model_config

    def test_child_does_not_share_config_with_parent(self):
        assert SimpleModel.model_config is not ChildModel.model_config


class TestOBIBaseModelStr:
    def test_str_equals_repr(self):
        obj = SimpleModel(value=42)
        assert str(obj) == repr(obj)


class TestOBIBaseModelInheritance:
    def test_is_pydantic_base_model(self):
        assert issubclass(OBIBaseModel, BaseModel)

    def test_subclass_is_base_model(self):
        assert issubclass(SimpleModel, BaseModel)
        assert issubclass(SimpleModel, OBIBaseModel)


class TestOBIBaseModelSerialization:
    def test_model_dump_includes_type(self):
        obj = SimpleModel(value=5)
        dump = obj.model_dump()
        assert dump["type"] == "SimpleModel"
        assert dump["value"] == 5

    def test_model_dump_json_includes_type(self):
        obj = SimpleModel(value=5)
        json_str = obj.model_dump_json()
        assert '"type":"SimpleModel"' in json_str or '"type": "SimpleModel"' in json_str

    def test_round_trip_serialization(self):
        obj = SimpleModel(value=42)
        dump = obj.model_dump()
        restored = SimpleModel.model_validate(dump)
        assert restored.value == obj.value
        assert restored.type == obj.type
