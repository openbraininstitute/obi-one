from unittest.mock import MagicMock
from uuid import UUID

from entitysdk.models import Species, TaskConfig

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod
from obi_one.scientific.from_id.species_from_id import SpeciesFromID

_TEST_ENTITY_ID = "00000000-0000-0000-0000-000000000001"
_TEST_ENTITY_UUID = UUID(_TEST_ENTITY_ID)


class ConcreteEntityFromID(EntityFromID[TaskConfig]):
    _entitysdk_type: type[TaskConfig] = TaskConfig


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
    def test_entitysdk_type_property(self):
        obj = ConcreteEntityFromID(id_str="xyz")
        assert obj.entitysdk_type is TaskConfig


class TestIdentifiableFromIDStr:
    def test_str_representation(self):
        obj = SpeciesFromID(id_str="species-1")
        assert str(obj) == "SpeciesFromID_species-1"


class TestEntityFromIDEntity:
    def test_entity_fetches_on_first_call(self):
        obj = ConcreteEntityFromID(id_str=_TEST_ENTITY_ID)
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result = obj.entity(mock_client)
        assert result == "entity_result"
        mock_client.get_entity.assert_called_once_with(
            entity_id=_TEST_ENTITY_UUID,
            entity_type=TaskConfig,
        )

    def test_entity_caches_result(self):
        obj = ConcreteEntityFromID(id_str=_TEST_ENTITY_ID)
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "entity_result"

        result1 = obj.entity(mock_client)
        result2 = obj.entity(mock_client)

        assert result1 == result2
        assert mock_client.get_entity.call_count == 1


class TestIdentifiableFromIDEntity:
    def test_entity_fetches_with_entitysdk_type(self):
        obj = SpeciesFromID(id_str=_TEST_ENTITY_ID)
        mock_client = MagicMock()
        mock_client.get_entity.return_value = "species_entity"

        result = obj.entity(mock_client)
        assert result == "species_entity"
        mock_client.get_entity.assert_called_once_with(
            entity_id=_TEST_ENTITY_UUID,
            entity_type=Species,
        )
