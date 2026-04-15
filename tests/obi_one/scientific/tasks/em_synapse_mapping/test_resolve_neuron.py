from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import resolve_neuron


@pytest.fixture
def morph_entity():
    return SimpleNamespace(id=uuid4(), name="test_morph")


@pytest.fixture
def source_mesh():
    return SimpleNamespace(
        dense_reconstruction_cell_id=42,
        em_dense_reconstruction_dataset=SimpleNamespace(id=uuid4()),
        release_version=3,
    )


@pytest.fixture
def source_dataset(source_mesh):
    return SimpleNamespace(id=source_mesh.em_dense_reconstruction_dataset.id, name="dataset")


class TestResolveNeuron:
    def test_resolve_morphology(
        self, tmp_path, mock_db_client, morph_entity, source_mesh, source_dataset
    ):
        morph_ref = Mock()
        morph_ref.entity.return_value = morph_entity

        mock_db_client.get_entity.return_value = source_dataset

        with (
            patch.object(morph_ref, "write_spiny_neuron_h5"),
            patch.object(
                morph_ref,
                "neurom_morphology",
                return_value=Mock(
                    to_morphio=Mock(
                        return_value=Mock(as_mutable=Mock(return_value=Mock(write=Mock())))
                    )
                ),
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron.load_morphology_with_spines",
                return_value="spiny_mock",
            ),
            patch.object(morph_ref, "source_mesh_entity", return_value=source_mesh),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron.isinstance",
                side_effect=lambda obj, cls: False,
            ) if False else patch.object(type(morph_ref), "__instancecheck__", return_value=False),
        ):
            # We need to make isinstance(neuron_ref, MEModelFromID) return False
            # The simplest way is to use a Mock that isn't an MEModelFromID
            from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

            morph_ref_real = Mock(spec=CellMorphologyFromID)
            morph_ref_real.entity.return_value = morph_entity
            morph_ref_real.write_spiny_neuron_h5 = Mock()
            morph_ref_real.neurom_morphology.return_value = Mock(
                to_morphio=Mock(
                    return_value=Mock(as_mutable=Mock(return_value=Mock(write=Mock())))
                )
            )
            morph_ref_real.source_mesh_entity.return_value = source_mesh

            with patch(
                "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron.load_morphology_with_spines",
                return_value="spiny_mock",
            ):
                result = resolve_neuron(morph_ref_real, mock_db_client, tmp_path)

        assert result.pt_root_id == 42
        assert result.morph_entity is morph_entity
        assert result.use_me_model is False
        assert result.spiny_morph == "spiny_mock"
        assert result.cave_version == 3
        assert result.fn_morph_h5 == Path("morphologies") / (morph_entity.name + ".h5")
        assert result.fn_morph_swc == Path("morphologies/morphology") / (
            morph_entity.name + ".swc"
        )

    def test_resolve_memodel(self, tmp_path, mock_db_client, morph_entity, source_mesh, source_dataset):
        from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

        me_model_entity = SimpleNamespace(
            morphology=morph_entity,
            calibration_result=SimpleNamespace(threshold_current=0.5, holding_current=0.1),
        )

        memodel_ref = Mock(spec=MEModelFromID)
        memodel_ref.entity.return_value = me_model_entity

        mock_db_client.get_entity.return_value = source_dataset

        mock_memodel_paths = SimpleNamespace(
            mechanisms_dir=tmp_path / "mechs",
            hoc_path=tmp_path / "model.hoc",
        )
        (tmp_path / "mechs").mkdir()
        (tmp_path / "model.hoc").touch()

        with (
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron.load_morphology_with_spines",
                return_value="spiny_mock",
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron.download_memodel",
                return_value=mock_memodel_paths,
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron.CellMorphologyFromID"
            ) as MockCMFromID,
            patch("shutil.move"),
            patch("shutil.rmtree"),
        ):
            mock_cm = MockCMFromID.return_value
            mock_cm.write_spiny_neuron_h5 = Mock()
            mock_cm.neurom_morphology.return_value = Mock(
                to_morphio=Mock(
                    return_value=Mock(as_mutable=Mock(return_value=Mock(write=Mock())))
                )
            )
            mock_cm.source_mesh_entity.return_value = source_mesh

            result = resolve_neuron(memodel_ref, mock_db_client, tmp_path)

        assert result.pt_root_id == 42
        assert result.use_me_model is True
        assert "model_template" in result.phys_node_props
        assert "threshold_current" in result.phys_node_props
        assert "holding_current" in result.phys_node_props
