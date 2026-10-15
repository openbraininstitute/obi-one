"""Tests for *FromID subclasses that narrow ``entity()`` return types."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from entitysdk.types import ContentType

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

FROM_ID_CLASSES = (
    MEModelFromID,
    CellMorphologyFromID,
    ETypeClassFromID,
    IonChannelModelFromID,
    SimulatableExtracellularRecordingArrayFromID,
)


class TestFromIDTypedEntity:
    @pytest.mark.parametrize("from_id_cls", FROM_ID_CLASSES)
    def test_entity_returns_resolved_entity(self, from_id_cls):
        obj = from_id_cls(id_str="00000000-0000-0000-0000-000000000001")
        expected = MagicMock()
        mock_client = MagicMock()
        mock_client.get_entity.return_value = expected
        result = obj.entity(mock_client)
        assert result is expected
        mock_client.get_entity.assert_called_once_with(
            entity_id=UUID(obj.id_str),
            entity_type=obj.entitysdk_type,
        )
        assert obj._entity is expected

    @pytest.mark.parametrize("from_id_cls", FROM_ID_CLASSES)
    def test_entity_caches_after_first_resolution(self, from_id_cls):
        obj = from_id_cls(id_str="00000000-0000-0000-0000-000000000002")
        expected = MagicMock()
        mock_client = MagicMock()
        mock_client.get_entity.return_value = expected
        assert obj.entity(mock_client) is expected
        assert obj.entity(mock_client) is expected
        mock_client.get_entity.assert_called_once()


class TestIonChannelModelFromIDTypedEntity:
    def test_get_conductance_name_uses_typed_entity(self):
        obj = IonChannelModelFromID(id_str="ic-id")
        entity = MagicMock(conductance_name="g_na")
        with patch.object(IonChannelModelFromID, "entity", return_value=entity):
            assert obj.get_conductance_name(MagicMock()) == "g_na"

    def test_get_max_permeability_name_uses_typed_entity(self):
        obj = IonChannelModelFromID(id_str="ic-id")
        entity = MagicMock(max_permeability_name="p_na")
        with patch.object(IonChannelModelFromID, "entity", return_value=entity):
            assert obj.get_max_permeability_name(MagicMock()) == "p_na"

    def test_get_other_parameter_names_excludes_conductance_and_permeability(self):
        obj = IonChannelModelFromID(id_str="ic-id")
        entity = MagicMock()
        entity.neuron_block.range = ["g_na", "p_na", "custom"]
        entity.conductance_name = "g_na"
        entity.max_permeability_name = "p_na"
        with patch.object(IonChannelModelFromID, "entity", return_value=entity):
            assert obj.get_other_parameter_names(MagicMock()) == ["custom"]

    def test_get_other_parameter_names_flattens_mapping_entries(self):
        obj = IonChannelModelFromID(id_str="ic-id")
        entity = MagicMock()
        entity.neuron_block.range = [["param_a", "g_na"]]
        entity.conductance_name = "g_na"
        entity.max_permeability_name = None
        with (
            patch.object(IonChannelModelFromID, "entity", return_value=entity),
            patch.object(IonChannelModelFromID, "get_conductance_name", return_value="g_na"),
            patch.object(IonChannelModelFromID, "get_max_permeability_name", return_value=None),
        ):
            assert obj.get_other_parameter_names(MagicMock()) == ["param_a"]

    def test_has_conductance_reflects_conductance_name(self):
        with patch.object(
            IonChannelModelFromID,
            "entity",
            return_value=MagicMock(conductance_name="g_na"),
        ):
            assert IonChannelModelFromID(id_str="ic-with-g").has_conductance(MagicMock()) is True
        with patch.object(
            IonChannelModelFromID,
            "entity",
            return_value=MagicMock(conductance_name=None),
        ):
            assert (
                IonChannelModelFromID(id_str="ic-without-g").has_conductance(MagicMock()) is False
            )

    def test_has_max_permeability_reflects_name(self):
        obj = IonChannelModelFromID(id_str="ic-id")
        with patch.object(
            IonChannelModelFromID,
            "entity",
            return_value=MagicMock(max_permeability_name="p_na"),
        ):
            assert obj.has_max_permeability(MagicMock()) is True

    def test_download_asset_returns_downloaded_path(self, tmp_path):
        obj = IonChannelModelFromID(id_str="ic-id")
        entity = MagicMock()
        asset = MagicMock(path=tmp_path / "channel.mod")
        mock_client = MagicMock()
        mock_client.download_assets.return_value.one.return_value = asset
        with patch.object(IonChannelModelFromID, "entity", return_value=entity):
            path = obj.download_asset(dest_dir=tmp_path, db_client=mock_client)
        assert path == asset.path
        mock_client.download_assets.assert_called_once_with(
            entity,
            selection={"content_type": ContentType.application_mod},
            output_path=tmp_path,
        )


class TestMEModelFromIDTypedEntity:
    def test_morphio_morphology_resolves_memodel_then_morphology(self):
        memodel = MagicMock()
        memodel.morphology.id = "morph-uuid"
        obj = MEModelFromID(id_str="me-id")
        mock_client = MagicMock()
        with (
            patch.object(MEModelFromID, "entity", return_value=memodel),
            patch(
                "obi_one.scientific.from_id.memodel_from_id.CellMorphologyFromID"
            ) as morphology_cls,
        ):
            morphology = morphology_cls.return_value
            morphology.morphio_morphology.return_value = "morphology"
            result = obj.morphio_morphology(mock_client)
        morphology_cls.assert_called_once_with(id_str="morph-uuid")
        assert result == "morphology"

    def test_stage_circuit_stages_sonata_from_memodel(self, tmp_path):
        obj = MEModelFromID(id_str="me-id")
        memodel = MagicMock()
        mock_client = MagicMock()
        dest_dir = tmp_path / "sonata_out"
        config_path = dest_dir / "circuit_config.json"
        with (
            patch.object(MEModelFromID, "entity", return_value=memodel),
            patch(
                "obi_one.scientific.from_id.memodel_from_id.stage_sonata_from_memodel",
                return_value=config_path,
            ) as mock_stage,
            patch(
                "obi_one.scientific.from_id.memodel_from_id.MEModelCircuit",
                side_effect=lambda name, path: SimpleNamespace(name=name, path=path),
            ),
        ):
            circuit = obj.stage_circuit(
                db_client=mock_client,
                dest_dir=dest_dir,
                entity_cache=False,
            )
        mock_stage.assert_called_once_with(
            client=mock_client,
            memodel=memodel,
            output_dir=dest_dir,
        )
        assert circuit.name == "single_cell"
        assert circuit.path == str(config_path)

    def test_stage_circuit_raises_when_dest_dir_exists_without_cache(self, tmp_path):
        obj = MEModelFromID(id_str="me-id")
        dest_dir = tmp_path / "existing"
        dest_dir.mkdir()
        with pytest.raises(FileExistsError, match="already exists"):
            obj.stage_circuit(db_client=MagicMock(), dest_dir=dest_dir, entity_cache=False)

    def test_stage_circuit_reads_existing_config_when_entity_cache(self, tmp_path):
        obj = MEModelFromID(id_str="me-id")
        dest_dir = tmp_path / "cached"
        dest_dir.mkdir()
        config_path = dest_dir / "circuit_config.json"
        config_path.write_text("{}")
        mock_client = MagicMock()
        with patch(
            "obi_one.scientific.from_id.memodel_from_id.MEModelCircuit",
            side_effect=lambda name, path: SimpleNamespace(name=name, path=path),
        ):
            circuit = obj.stage_circuit(
                db_client=mock_client,
                dest_dir=dest_dir,
                entity_cache=True,
            )
        mock_client.get_entity.assert_not_called()
        assert circuit.path == str(config_path)
