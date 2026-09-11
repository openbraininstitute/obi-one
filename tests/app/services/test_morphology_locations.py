from unittest.mock import MagicMock, patch
from uuid import uuid4

import entitysdk.client
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, Circuit, MEModel

import obi_one as obi
from app.services.morphology_locations import (
    preview_morphology_locations,
    resolve_morphology,
)
from obi_one.scientific.library.morphology_loader import load_morphology_nrn_order

from tests.utils import SINGLE_NEURON_CIRCUIT_DIR

SERVICE_MODULE = "app.services.morphology_locations"

MORPHOLOGY_PATH = (
    SINGLE_NEURON_CIRCUIT_DIR
    / "SingleNeuronCircuit__top_nodes_dim6__IDX0"
    / "morphologies"
    / "swc"
    / "dend-Fluo18_lower_axon-rp110127_L5-3_idC.swc"
)


def _entity_lookup(entities):
    def get_entity(*, entity_id, entity_type):
        del entity_id
        try:
            return entities[entity_type]
        except KeyError as exc:
            msg = "not found"
            raise EntitySDKError(msg) from exc

    return get_entity


@pytest.fixture(scope="module")
def morphology():
    return load_morphology_nrn_order(MORPHOLOGY_PATH)


class TestResolveMorphology:
    @patch(f"{SERVICE_MODULE}.load_memodel_morphology")
    def test_memodel(self, mock_load):
        entity_id = uuid4()
        memodel = MEModel.model_construct(id=entity_id)
        client = MagicMock(entitysdk.client.Client)
        client.get_entity.side_effect = _entity_lookup({MEModel: memodel})

        assert resolve_morphology(client, entity_id) is mock_load.return_value

        mock_load.assert_called_once_with(client, memodel)

    @patch(f"{SERVICE_MODULE}.load_cell_morphology")
    def test_cell_morphology(self, mock_load):
        entity_id = uuid4()
        cell_morphology = CellMorphology.model_construct(id=entity_id, assets=[])
        client = MagicMock(entitysdk.client.Client)
        client.get_entity.side_effect = _entity_lookup({CellMorphology: cell_morphology})

        assert resolve_morphology(client, entity_id) is mock_load.return_value

        mock_load.assert_called_once_with(client, cell_morphology)

    @patch(f"{SERVICE_MODULE}.load_single_neuron_circuit_morphology")
    def test_single_neuron_circuit(self, mock_load):
        entity_id = uuid4()
        circuit = Circuit.model_construct(id=entity_id, number_neurons=1)
        client = MagicMock(entitysdk.client.Client)
        client.get_entity.side_effect = _entity_lookup({Circuit: circuit})

        assert resolve_morphology(client, entity_id) is mock_load.return_value

        mock_load.assert_called_once_with(client, circuit)

    def test_an_unknown_entity_is_rejected(self):
        client = MagicMock(entitysdk.client.Client)
        client.get_entity.side_effect = _entity_lookup({})

        with pytest.raises(EntitySDKError, match="is not an MEModel"):
            resolve_morphology(client, uuid4())


class TestPreviewMorphologyLocations:
    @staticmethod
    def _preview(morphology, block):
        with patch(f"{SERVICE_MODULE}.resolve_morphology", return_value=morphology):
            return preview_morphology_locations(MagicMock(entitysdk.client.Client), uuid4(), block)

    @pytest.mark.parametrize(
        ("block", "expected_count"),
        [
            (obi.RandomMorphologyLocations(random_seed=0, number_of_locations=5), 5),
            (
                obi.ClusteredMorphologyLocations(
                    random_seed=0, number_of_locations=6, n_clusters=2
                ),
                6,
            ),
            (
                obi.PathDistanceMorphologyLocations(random_seed=0, number_of_locations=4),
                4,
            ),
        ],
        ids=["random", "clustered", "path_distance"],
    )
    def test_parametric_blocks_generate_locations_on_the_morphology(
        self, morphology, block, expected_count
    ):
        rows = self._preview(morphology, block.model_copy(deep=True))

        assert len(rows) == expected_count
        section_count = len(morphology.sections)
        for section_id, offset in rows:
            # SONATA numbering: 0 is the soma, neurites are 1..section_count.
            assert 0 <= section_id <= section_count
            assert 0.0 <= offset <= 1.0

    def test_explicit_points_are_returned_as_given(self, morphology):
        block = obi.ExplicitMorphologyLocations(
            locations=(
                obi.MorphologyLocationPoint(section_id=0, offset=0.0),
                obi.MorphologyLocationPoint(section_id=5, offset=0.5),
            )
        )

        rows = self._preview(morphology, block)

        assert rows == [(0, 0.0), (5, 0.5)]

    def test_the_same_seed_previews_the_same_locations(self, morphology):
        """The preview is only useful if the run places its points in the same spots."""
        block = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=5)

        first = self._preview(morphology, block.model_copy(deep=True))
        second = self._preview(morphology, block.model_copy(deep=True))

        assert first == second

    def test_a_different_seed_previews_different_locations(self, morphology):
        first = self._preview(
            morphology, obi.RandomMorphologyLocations(random_seed=0, number_of_locations=5)
        )
        second = self._preview(
            morphology, obi.RandomMorphologyLocations(random_seed=1, number_of_locations=5)
        )

        assert first != second

    def test_section_types_restrict_where_locations_land(self, morphology):
        basal_only = obi.RandomMorphologyLocations(
            random_seed=0, number_of_locations=8, section_types=(3,)
        )

        rows = self._preview(morphology, basal_only)

        basal_dendrite = 3
        # section_id - 1 undoes the SONATA soma offset to index morphio's section list.
        assert {int(morphology.sections[section_id - 1].type) for section_id, _ in rows} == {
            basal_dendrite
        }

    def test_a_parameter_sweep_is_rejected_before_the_morphology_is_resolved(self):
        """Resolution downloads assets, so an unusable request must fail before it."""
        block = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=[3, 5])

        with (
            patch(f"{SERVICE_MODULE}.resolve_morphology") as mock_resolve,
            pytest.raises(TypeError),
        ):
            preview_morphology_locations(MagicMock(entitysdk.client.Client), uuid4(), block)

        mock_resolve.assert_not_called()
