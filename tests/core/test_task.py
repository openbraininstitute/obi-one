import pytest

from obi_one.core.base import OBIBaseModel
from obi_one.core.task import Task


class ConcreteTask(Task):
    value: int = 0


class TestTask:
    def test_task_is_subclass_of_obi_base_model(self):
        assert issubclass(Task, OBIBaseModel)

    def test_concrete_task_creation(self):
        task = ConcreteTask(value=42)
        assert task.value == 42

    def test_type_field(self):
        task = ConcreteTask()
        assert task.type == "ConcreteTask"

    def test_json_schema_extra_has_ui_enabled_false(self):
        assert Task.json_schema_extra_additions == {"ui_enabled": False}

    def test_ui_enabled_propagated_to_schema(self):
        schema_extra = ConcreteTask.model_config.get("json_schema_extra")
        assert schema_extra.get("ui_enabled") is False
