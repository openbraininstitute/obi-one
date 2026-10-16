import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import morphio
import neurom
import numpy as np
import pytest

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import (
    ResolvedEMDataset,
    ResolvedNeuron,
    place_morphologies_and_mechanisms,
    resolve_list_neurons,
    write_morphology_with_offset,
)

_MODULE = "obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron"

# Example morphology shipped with the repo, used for the round-trip offset test.
_EXAMPLE_MORPHOLOGY = (
    Path(__file__).parents[5]
    / "examples"
    / "data"
    / "morphologies"
    / "L5_TPC:A_MusMusculus_PrimarySomatosensory_C060114A5"
    / "C060114A5.swc"
)


def _mock_morphio_chain():
    """A neurom-like morphology whose morphio chain accepts write()."""
    mutable = Mock()
    mutable.soma.points = np.zeros((1, 3), dtype=float)
    mutable.iter.return_value = []
    return Mock(to_morphio=Mock(return_value=Mock(as_mutable=Mock(return_value=mutable))))


def _spiny_morph():
    return Mock(morphology=_mock_morphio_chain())


@pytest.fixture
def mock_db_client():
    return Mock()


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


def _make_resolved_neuron(pt_root_id, name):
    return ResolvedNeuron(
        pt_root_id=pt_root_id,
        morph_entity=SimpleNamespace(id=uuid4(), name=name),
        morph_from_id=Mock(),
        spiny_morph=Mock(),
        smooth_morph=Mock(),
        source_mesh_entity=Mock(),
        source_dataset=SimpleNamespace(id=uuid4(), name="ds"),
        cave_version=3,
        use_me_model=False,
        name_in_circuit=str(pt_root_id),
        phys_node_props={},
        fn_morph_h5=Path(f"{name}.h5"),
        fn_morph_swc=Path(f"morphologies/morphology/{name}.swc"),
    )


class TestResolvedEMDataset:
    """Dataset consistency validation moved into ResolvedEMDataset."""

    def test_sets_initial_values(self):
        rds = ResolvedEMDataset(cave_version_=None, dataset_from_id_=None)
        ds = SimpleNamespace(id_str="ds-1")
        rds.dataset_from_id = ds
        rds.cave_version = 3
        assert rds.dataset_from_id is ds
        assert rds.cave_version == 3
        assert rds.source_dataset_id == "ds-1"

    def test_rejects_mixed_datasets(self):
        rds = ResolvedEMDataset(cave_version_=None, dataset_from_id_=None)
        rds.dataset_from_id = SimpleNamespace(id_str="ds-1")
        with pytest.raises(ValueError, match="different EM datasets"):
            rds.dataset_from_id = SimpleNamespace(id_str="ds-2")

    def test_rejects_mixed_versions(self):
        rds = ResolvedEMDataset(cave_version_=None, dataset_from_id_=None)
        rds.cave_version = 3
        with pytest.raises(ValueError, match="different release versions"):
            rds.cave_version = 7


class TestPlaceMorphologiesAndMechanisms:
    def test_place_morphology_only(
        self, tmp_path, mock_db_client, morph_entity, source_mesh, source_dataset
    ):
        morph_from_id = Mock(spec=CellMorphologyFromID)
        morph_from_id.entity.return_value = morph_entity
        morph_from_id.write_spiny_neuron_h5 = Mock()
        morph_from_id.neurom_morphology.return_value = _mock_morphio_chain()

        with patch(f"{_MODULE}.load_morphology_with_spines", return_value=_spiny_morph()):
            result, mechanisms_placed = place_morphologies_and_mechanisms(
                morph_from_id=morph_from_id,
                me_model_entity=None,
                source_mesh_entity=source_mesh,
                source_dataset=source_dataset,
                pt_root_id=42,
                xyz=np.zeros(3),
                db_client=mock_db_client,
                out_root=tmp_path,
                spiny_morph_out_root=tmp_path,
            )

        assert result.pt_root_id == 42
        assert result.morph_entity is morph_entity
        assert result.use_me_model is False
        assert result.cave_version == 3
        assert result.fn_morph_h5 == Path(str(morph_entity.id) + ".h5")
        assert result.fn_morph_swc == Path("morphologies/morphology") / (
            str(morph_entity.id) + ".swc"
        )
        assert mechanisms_placed is None

    def test_place_with_me_model(
        self, tmp_path, mock_db_client, morph_entity, source_mesh, source_dataset
    ):
        me_model_entity = SimpleNamespace(
            id=uuid4(),
            morphology=morph_entity,
            calibration_result=SimpleNamespace(threshold_current=0.5, holding_current=0.1),
        )

        morph_from_id = Mock(spec=CellMorphologyFromID)
        morph_from_id.entity.return_value = morph_entity
        morph_from_id.write_spiny_neuron_h5 = Mock()
        morph_from_id.neurom_morphology.return_value = _mock_morphio_chain()

        mock_memodel_paths = SimpleNamespace(
            mechanisms_dir=tmp_path / "mechs",
            hoc_path=tmp_path / "model.hoc",
        )
        (tmp_path / "mechs").mkdir()
        (tmp_path / "model.hoc").touch()

        with (
            patch(f"{_MODULE}.load_morphology_with_spines", return_value=_spiny_morph()),
            patch(f"{_MODULE}.download_memodel", return_value=mock_memodel_paths),
            patch("shutil.move"),
            patch("shutil.rmtree"),
        ):
            result, mechanisms_placed = place_morphologies_and_mechanisms(
                morph_from_id=morph_from_id,
                me_model_entity=me_model_entity,
                source_mesh_entity=source_mesh,
                source_dataset=source_dataset,
                pt_root_id=42,
                xyz=np.zeros(3),
                db_client=mock_db_client,
                out_root=tmp_path,
                spiny_morph_out_root=tmp_path,
            )

        assert result.pt_root_id == 42
        assert result.use_me_model is True
        assert "model_template" in result.phys_node_props
        assert "@dynamics:threshold_current" in result.phys_node_props
        assert "@dynamics:holding_current" in result.phys_node_props
        assert mechanisms_placed == "mod"


class TestResolveListNeurons:
    def test_resolve_single_morphology(self, tmp_path, mock_db_client, source_mesh, source_dataset):
        morph_ref = Mock(spec=CellMorphologyFromID)
        rn = _make_resolved_neuron(42, "neuron_A")

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch(
                f"{_MODULE}.resolve_provenance",
                return_value=(42, source_mesh, source_dataset),
            ),
            patch(f"{_MODULE}.EMDataSetFromID") as mock_em_ds,
            patch(f"{_MODULE}.default_node_spec_for", return_value={}),
            patch(
                f"{_MODULE}.assemble_collection_from_specs",
                return_value=(SimpleNamespace(properties={}, positions=None), []),
            ),
            patch(
                f"{_MODULE}.place_morphologies_and_mechanisms",
                return_value=(rn, None),
            ) as mock_place,
        ):
            mock_em_ds.return_value = SimpleNamespace(id_str="ds-1")
            resolved_neurons, resolved_em_dataset, coll_bio, mechanisms_placed = (
                resolve_list_neurons(
                    init_neurons=[morph_ref],
                    db_client=mock_db_client,
                    out_root=tmp_path,
                    spiny_dir=tmp_path,
                )
            )

        assert resolved_neurons == [rn]
        assert resolved_em_dataset.cave_version == 3
        assert mechanisms_placed is None
        assert list(coll_bio.properties["morphology"]) == ["morphology/42"]
        mock_place.assert_called_once()

    def test_resolve_memodel_runs_place_morphologies(
        self, tmp_path, mock_db_client, morph_entity, source_mesh, source_dataset
    ):
        me_model_entity = SimpleNamespace(
            id=uuid4(),
            morphology=morph_entity,
            calibration_result=SimpleNamespace(threshold_current=0.5, holding_current=0.1),
        )
        memodel_ref = Mock(spec=MEModelFromID)
        memodel_ref.entity.return_value = me_model_entity
        morph_from_id = Mock(spec=CellMorphologyFromID)
        morph_from_id.entity.return_value = morph_entity
        morph_from_id.write_spiny_neuron_h5 = Mock()
        morph_from_id.neurom_morphology.return_value = _mock_morphio_chain()

        mock_memodel_paths = SimpleNamespace(
            mechanisms_dir=tmp_path / "mechs",
            hoc_path=tmp_path / "model.hoc",
        )
        (tmp_path / "mechs").mkdir()
        (tmp_path / "model.hoc").touch()

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch(
                f"{_MODULE}.resolve_provenance",
                return_value=(42, source_mesh, source_dataset),
            ),
            patch(f"{_MODULE}.EMDataSetFromID", return_value=SimpleNamespace(id_str="ds-1")),
            patch(f"{_MODULE}.default_node_spec_for", return_value={}),
            patch(
                f"{_MODULE}.assemble_collection_from_specs",
                return_value=(SimpleNamespace(properties={}, positions=np.zeros((1, 3))), []),
            ),
            patch(f"{_MODULE}.CellMorphologyFromID", return_value=morph_from_id),
            patch(f"{_MODULE}.load_morphology_with_spines", return_value=_spiny_morph()),
            patch(f"{_MODULE}.download_memodel", return_value=mock_memodel_paths),
            patch("shutil.move"),
            patch("shutil.rmtree"),
        ):
            resolved_neurons, _resolved_em_dataset, _coll_bio, mechanisms_placed = (
                resolve_list_neurons(
                    init_neurons=[memodel_ref],
                    db_client=mock_db_client,
                    out_root=tmp_path,
                    spiny_dir=tmp_path,
                )
            )

        assert resolved_neurons[0].use_me_model is True
        assert mechanisms_placed is not None

    def test_resolve_memodel_resolves_morphology(
        self, tmp_path, mock_db_client, morph_entity, source_mesh, source_dataset
    ):
        me_model_entity = SimpleNamespace(morphology=morph_entity)
        memodel_ref = Mock(spec=MEModelFromID)
        memodel_ref.entity.return_value = me_model_entity
        rn = _make_resolved_neuron(42, "neuron_A")

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch(
                f"{_MODULE}.resolve_provenance",
                return_value=(42, source_mesh, source_dataset),
            ),
            patch(f"{_MODULE}.EMDataSetFromID") as mock_em_ds,
            patch(f"{_MODULE}.default_node_spec_for", return_value={}),
            patch(
                f"{_MODULE}.assemble_collection_from_specs",
                return_value=(SimpleNamespace(properties={}, positions=None), []),
            ),
            patch(f"{_MODULE}.CellMorphologyFromID") as mock_cm_from_id,
            patch(
                f"{_MODULE}.place_morphologies_and_mechanisms",
                return_value=(rn, "mod"),
            ) as mock_place,
        ):
            mock_em_ds.return_value = SimpleNamespace(id_str="ds-1")
            resolved_neurons, _resolved_em_dataset, _coll_bio, mechanisms_placed = (
                resolve_list_neurons(
                    init_neurons=[memodel_ref],
                    db_client=mock_db_client,
                    out_root=tmp_path,
                    spiny_dir=tmp_path,
                )
            )

        # The ME model's morphology is wrapped in a CellMorphologyFromID.
        mock_cm_from_id.assert_called_once_with(id_str=str(morph_entity.id))
        # The ME model entity is forwarded to the placement step.
        assert mock_place.call_args.kwargs["me_model_entity"] is me_model_entity
        assert resolved_neurons == [rn]
        assert mechanisms_placed == "mod"

    def test_rejects_mixed_datasets(self, tmp_path, mock_db_client, source_mesh):
        morph_ref_1 = Mock(spec=CellMorphologyFromID)
        morph_ref_2 = Mock(spec=CellMorphologyFromID)
        ds_1 = SimpleNamespace(id=uuid4(), name="ds-1")
        ds_2 = SimpleNamespace(id=uuid4(), name="ds-2")

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch(
                f"{_MODULE}.resolve_provenance",
                side_effect=[(42, source_mesh, ds_1), (43, source_mesh, ds_2)],
            ),
            patch(
                f"{_MODULE}.EMDataSetFromID",
                side_effect=[SimpleNamespace(id_str="ds-1"), SimpleNamespace(id_str="ds-2")],
            ),
            pytest.raises(ValueError, match="different EM datasets"),
        ):
            resolve_list_neurons(
                init_neurons=[morph_ref_1, morph_ref_2],
                db_client=mock_db_client,
                out_root=tmp_path,
                spiny_dir=tmp_path,
            )

    def test_rejects_duplicate_pt_root_ids(
        self, tmp_path, mock_db_client, source_mesh, source_dataset
    ):
        morph_ref_1 = Mock(spec=CellMorphologyFromID)
        morph_ref_2 = Mock(spec=CellMorphologyFromID)

        rn1 = _make_resolved_neuron(111, "neuron_A")
        rn2 = _make_resolved_neuron(111, "neuron_B")  # duplicate pt_root_id

        with (
            patch.dict(os.environ, {"CAVECLIENT_MICRONS_API_KEY": "fake-key"}),
            patch(
                f"{_MODULE}.resolve_provenance",
                side_effect=[
                    (111, source_mesh, source_dataset),
                    (111, source_mesh, source_dataset),
                ],
            ),
            patch(f"{_MODULE}.EMDataSetFromID", return_value=SimpleNamespace(id_str="ds-1")),
            patch(f"{_MODULE}.default_node_spec_for", return_value={}),
            patch(
                f"{_MODULE}.assemble_collection_from_specs",
                return_value=(SimpleNamespace(properties={}, positions=None), []),
            ),
            patch(
                f"{_MODULE}.place_morphologies_and_mechanisms",
                side_effect=[(rn1, None), (rn2, None)],
            ),
            pytest.raises(ValueError, match=r"Duplicate pt_root_id 111.*neuron_B.*neuron_A"),
        ):
            resolve_list_neurons(
                init_neurons=[morph_ref_1, morph_ref_2],
                db_client=mock_db_client,
                out_root=tmp_path,
                spiny_dir=tmp_path,
            )


class TestWriteMorphologyWithOffset:
    def test_offset_applied_to_all_points(self, tmp_path):
        """Round-trip: load a real morphology, write it with an offset, read it back.

        Every soma and section point in the written file must equal the original
        coordinate plus the applied offset.
        """
        assert _EXAMPLE_MORPHOLOGY.exists(), f"Missing test morphology: {_EXAMPLE_MORPHOLOGY}"

        # Reference copy to compare against (independent of the object passed in).
        original = morphio.Morphology(_EXAMPLE_MORPHOLOGY)

        # The function expects a neurom.Morphology.
        morph = neurom.load_morphology(_EXAMPLE_MORPHOLOGY)

        offset = np.array([100.0, 100.0, 100.0], dtype=np.float32)
        out_path = tmp_path / "offset.swc"
        write_morphology_with_offset(morph, offset, out_path)

        assert out_path.exists()
        result = morphio.Morphology(out_path)

        # Soma points are offset.
        np.testing.assert_allclose(
            result.soma.points, original.soma.points + offset, rtol=1e-4, atol=1e-3
        )

        # Same number of sections, each with points offset by the same amount.
        original_sections = list(original.iter())
        result_sections = list(result.iter())
        assert len(result_sections) == len(original_sections)
        assert len(result_sections) > 0

        for orig_sec, res_sec in zip(original_sections, result_sections, strict=True):
            np.testing.assert_allclose(
                res_sec.points, orig_sec.points + offset, rtol=1e-4, atol=1e-3
            )
