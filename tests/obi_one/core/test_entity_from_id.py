from unittest.mock import MagicMock

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod


class TestLoadAssetMethod:
    def test_memory_value(self):
        assert LoadAssetMethod.MEMORY.value == "memory"

    def test_file_value(self):
        assert LoadAssetMethod.FILE.value == "file"


class TestEntityFromIDStr:
    def test_str_representation(self):
        class ConcreteEntityFromID(EntityFromID):
            type: str = "EntityFromID"
            entitysdk_class = MagicMock()

        obj = ConcreteEntityFromID(id_str="abc-123")
        assert str(obj) == "ConcreteEntityFromID_abc-123"


class TestEntityFromIDProperties:
    def test_entitysdk_type_returns_class_variable(self):
        mock_class = MagicMock()

        class ConcreteEntityFromID(EntityFromID):
            type: str = "EntityFromID"
            entitysdk_class = mock_class

        obj = ConcreteEntityFromID(id_str="xyz")
        assert obj.entitysdk_type is mock_class


class TestEntityFromIDFetch:
    def test_fetch_calls_db_client(self):
        mock_entity_class = MagicMock()

        class ConcreteEntityFromID(EntityFromID):
            entitysdk_class = mock_entity_class

        mock_client = MagicMock()
        mock_client.get_entity.return_value = "fetched_entity"

        result = ConcreteEntityFromID.fetch("entity-id-1", mock_client)
        mock_client.get_entity.assert_called_once_with(
            entity_id="entity-id-1", entity_type=mock_entity_class
        )
        assert result == "fetched_entity"


class TestEntityFromIDEntity:
    def test_entity_fetches_on_first_call(self):
        mock_entity_class = MagicMock()

        class ConcreteEntityFromID(EntityFromID):
            type: str = "EntityFromID"
            entitysdk_class = mock_entity_class

        obj = ConcreteEntityFromID(id_str="test-id")
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result = obj.entity(mock_client)
        assert result == "entity_result"
        mock_client.get_entity.assert_called_once()

    def test_entity_caches_result(self):
        mock_entity_class = MagicMock()

        class ConcreteEntityFromID(EntityFromID):
            type: str = "EntityFromID"
            entitysdk_class = mock_entity_class

        obj = ConcreteEntityFromID(id_str="test-id")
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        # Call twice
        result1 = obj.entity(mock_client)
        result2 = obj.entity(mock_client)

        # Should only fetch once
        assert result1 == result2
        assert mock_client.get_entity.call_count == 1
