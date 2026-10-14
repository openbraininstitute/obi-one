from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from entitysdk.models import TaskConfig

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod

_TEST_ENTITY_ID = "00000000-0000-0000-0000-000000000001"
_TEST_ENTITY_UUID = UUID(_TEST_ENTITY_ID)


class ConcreteEntityFromID(EntityFromID[TaskConfig]):
    @classmethod
    def entitysdk_class(cls) -> type[TaskConfig]:
        return TaskConfig


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

        result = ConcreteEntityFromID.fetch(_TEST_ENTITY_ID, mock_client)
        mock_client.get_entity.assert_called_once_with(
            entity_id=_TEST_ENTITY_UUID, entity_type=TaskConfig
        )
        assert result == "fetched_entity"


class TestEntityFromIDEntity:
    def test_entity_fetches_on_first_call(self):
        obj = ConcreteEntityFromID(id_str=_TEST_ENTITY_ID)
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result = obj.entity(mock_client)
        assert result == "entity_result"
        mock_client.get_entity.assert_called_once()

    def test_entity_caches_result(self):
        obj = ConcreteEntityFromID(id_str=_TEST_ENTITY_ID)
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result1 = obj.entity(mock_client)
        result2 = obj.entity(mock_client)

        assert result1 == result2
        assert mock_client.get_entity.call_count == 1

    def test_entity_raises_when_fetch_returns_none(self):
        obj = ConcreteEntityFromID(id_str=_TEST_ENTITY_ID)
        with (
            patch.object(ConcreteEntityFromID, "fetch", return_value=None),
            pytest.raises(RuntimeError, match=f"failed to resolve entity {_TEST_ENTITY_ID!r}"),
        ):
            obj.entity(MagicMock())
