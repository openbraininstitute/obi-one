from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.models import TaskConfig

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod


class ConcreteEntityFromID(EntityFromID[TaskConfig]):
    entitysdk_class: ClassVar[type[TaskConfig]] = TaskConfig  # noqa: A003


class TestLoadAssetMethod:
    def test_memory_value(self):
        assert LoadAssetMethod.MEMORY.value == "memory"

    def test_file_value(self):
        assert LoadAssetMethod.FILE.value == "file"


class TestEntityFromIDStr:
    def test_str_representation(self):
        obj = ConcreteEntityFromID(id_str="abc-123")
        assert str(obj) == "ConcreteEntityFromID_abc-123"


class TestEntityFromIDProperties:
    def test_entitysdk_type_returns_class_variable(self):
        obj = ConcreteEntityFromID(id_str="xyz")
        assert obj.entitysdk_type is TaskConfig


class TestEntityFromIDFetch:
    def test_fetch_calls_db_client(self):
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "fetched_entity"

        result = ConcreteEntityFromID.fetch("entity-id-1", mock_client)
        mock_client.get_entity.assert_called_once_with(
            entity_id="entity-id-1", entity_type=TaskConfig
        )
        assert result == "fetched_entity"


class TestEntityFromIDEntity:
    def test_entity_fetches_on_first_call(self):
        obj = ConcreteEntityFromID(id_str="test-id")
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result = obj.entity(mock_client)
        assert result == "entity_result"
        mock_client.get_entity.assert_called_once()

    def test_entity_caches_result(self):
        obj = ConcreteEntityFromID(id_str="test-id")
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result1 = obj.entity(mock_client)
        result2 = obj.entity(mock_client)

        assert result1 == result2
        assert mock_client.get_entity.call_count == 1

    def test_entity_raises_when_fetch_returns_none(self):
        obj = ConcreteEntityFromID(id_str="missing-id")
        with (
            patch.object(ConcreteEntityFromID, "fetch", return_value=None),
            pytest.raises(RuntimeError, match="failed to resolve entity 'missing-id'"),
        ):
            obj.entity(MagicMock())
