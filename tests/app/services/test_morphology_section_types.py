import json
import shutil
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import entitysdk.client
import morphio
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, Circuit, MEModel
from entitysdk.types import AssetLabel, CircuitScale, ContentType

from app.schemas.morphology_section_types import MorphologySectionTypeOption
from app.services.morphology_section_types import (
    cell_morphology_section_type_options,
    memodel_section_type_options,
    memodel_with_synapses_section_type_options,
    morphology_source_section_type_options,
    section_type_options,
)

from tests.utils import DATA_DIR, SINGLE_NEURON_CIRCUIT_DIR

SERVICE_MODULE = "app.services.morphology_section_types"


def _values_and_labels(options):
    return [(option.value, option.label) for option in options]


def _entity_lookup(entities):
    def get_entity(*, entity_id, entity_type):
        del entity_id
        try:
            return entities[entity_type]
        except KeyError as exc:
            msg = "not found"
            raise EntitySDKError(msg) from exc

    return get_entity


def test_section_type_options_only_returns_present_target_types():
    morphology = morphio.Morphology(DATA_DIR / "cell_morphology.asc")

    assert _values_and_labels(section_type_options(morphology)) == [
        (2, "Axon"),
        (3, "Basal dendrite"),
    ]


def test_cell_morphology_section_type_options():
    morphology = CellMorphology.model_validate(
        json.loads((DATA_DIR / "cell_morphology.json").read_bytes())
    )
    spiny_asset = MagicMock()
    spiny_asset.id = uuid4()
    spiny_asset.content_type = ContentType.application_x_hdf5
    spiny_asset.label = AssetLabel.morphology_with_spines
    morphology.assets.insert(0, spiny_asset)
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = morphology
    client.download_content.return_value = (DATA_DIR / "cell_morphology.swc").read_bytes()

    options = cell_morphology_section_type_options(client, morphology.id)

    assert _values_and_labels(options) == [
        (2, "Axon"),
        (3, "Basal dendrite"),
        (4, "Apical dendrite"),
    ]
    client.get_entity.assert_called_once_with(
        entity_id=morphology.id,
        entity_type=CellMorphology,
    )
    client.download_content.assert_called_once_with(
        entity_id=morphology.id,
        entity_type=CellMorphology,
        asset_id=morphology.assets[1].id,
    )


def test_cell_morphology_requires_id():
    morphology_id = uuid4()
    morphology = CellMorphology.model_construct(id=None, assets=[])
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = morphology

    with pytest.raises(ValueError, match="missing an id"):
        cell_morphology_section_type_options(client, morphology_id)


def test_cell_morphology_requires_supported_asset():
    morphology_id = uuid4()
    unsupported_asset = MagicMock(
        content_type=ContentType.application_octet_stream,
        label=AssetLabel.morphology,
    )
    morphology = CellMorphology.model_construct(
        id=morphology_id,
        assets=[unsupported_asset],
    )
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = morphology

    with pytest.raises(ValueError, match="no supported SWC, H5, or ASC asset"):
        cell_morphology_section_type_options(client, morphology_id)


def test_cell_morphology_asset_requires_id():
    morphology_id = uuid4()
    asset = MagicMock(
        id=None,
        content_type=ContentType.application_swc,
        label=AssetLabel.morphology,
    )
    morphology = CellMorphology.model_construct(id=morphology_id, assets=[asset])
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = morphology

    with pytest.raises(ValueError, match="Morphology asset is missing an id"):
        cell_morphology_section_type_options(client, morphology_id)


def test_memodel_section_type_options_uses_linked_morphology():
    morphology = CellMorphology.model_validate(
        json.loads((DATA_DIR / "cell_morphology.json").read_bytes())
    )
    memodel = MagicMock(spec=MEModel)
    memodel.morphology = morphology
    memodel_id = uuid4()
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = memodel
    client.download_content.return_value = (DATA_DIR / "cell_morphology.swc").read_bytes()

    options = memodel_section_type_options(client, memodel_id)

    assert _values_and_labels(options) == [
        (2, "Axon"),
        (3, "Basal dendrite"),
        (4, "Apical dendrite"),
    ]
    client.get_entity.assert_called_once_with(entity_id=memodel_id, entity_type=MEModel)


def test_memodel_section_type_options_fetches_linked_morphology():
    memodel_id = uuid4()
    morphology_id = uuid4()
    linked_morphology = CellMorphology.model_construct(id=morphology_id, assets=[])
    downloaded_morphology = CellMorphology.model_validate(
        json.loads((DATA_DIR / "cell_morphology.json").read_bytes())
    )
    memodel = MagicMock(spec=MEModel)
    memodel.morphology = linked_morphology
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.side_effect = [memodel, downloaded_morphology]
    client.download_content.return_value = (DATA_DIR / "cell_morphology.swc").read_bytes()

    options = memodel_section_type_options(client, memodel_id)

    assert _values_and_labels(options) == [
        (2, "Axon"),
        (3, "Basal dendrite"),
        (4, "Apical dendrite"),
    ]
    assert client.get_entity.call_args_list == [
        call(entity_id=memodel_id, entity_type=MEModel),
        call(entity_id=morphology_id, entity_type=CellMorphology),
    ]


def test_memodel_linked_morphology_requires_id():
    memodel_id = uuid4()
    memodel = MagicMock(spec=MEModel)
    memodel.morphology = CellMorphology.model_construct(id=None, assets=[])
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = memodel

    with pytest.raises(ValueError, match="MEModel morphology is missing an id"):
        memodel_section_type_options(client, memodel_id)


def test_memodel_with_synapses_section_type_options():
    source_dir = SINGLE_NEURON_CIRCUIT_DIR / "SingleNeuronCircuit__top_nodes_dim6__IDX0"
    circuit_id = uuid4()
    asset_id = uuid4()
    circuit = Circuit.model_construct(
        id=circuit_id,
        scale=CircuitScale.single,
        number_neurons=1,
        has_morphologies=True,
    )
    asset = MagicMock()
    asset.id = asset_id
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = circuit
    client.select_assets.return_value.one.return_value = asset

    def copy_asset(*, output_path, asset_path, **_kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_dir / asset_path, output_path)

    client.download_file.side_effect = copy_asset

    options = memodel_with_synapses_section_type_options(client, circuit_id)

    assert _values_and_labels(options) == [
        (2, "Axon"),
        (3, "Basal dendrite"),
        (4, "Apical dendrite"),
    ]
    client.get_entity.assert_called_once_with(entity_id=circuit_id, entity_type=Circuit)
    downloaded_asset_paths = {
        str(call_.kwargs["asset_path"]) for call_ in client.download_file.call_args_list
    }
    assert downloaded_asset_paths == {
        "circuit_config.json",
        "S1nonbarrel_neurons/nodes.h5",
        "morphologies/swc/dend-Fluo18_lower_axon-rp110127_L5-3_idC.swc",
    }


def test_memodel_with_synapses_rejects_general_circuit():
    circuit_id = uuid4()
    circuit = Circuit.model_construct(
        id=circuit_id,
        scale=CircuitScale.small,
        number_neurons=10,
        has_morphologies=True,
    )
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = circuit

    with pytest.raises(ValueError, match="single-neuron circuit"):
        memodel_with_synapses_section_type_options(client, circuit_id)

    client.select_assets.assert_not_called()
    client.download_file.assert_not_called()


@pytest.mark.parametrize(
    ("circuit", "message"),
    [
        (
            Circuit.model_construct(
                id=None,
                scale=CircuitScale.single,
                number_neurons=1,
                has_morphologies=True,
            ),
            "missing an id",
        ),
        (
            Circuit.model_construct(
                id=uuid4(),
                scale=CircuitScale.single,
                number_neurons=1,
                has_morphologies=False,
            ),
            "has no morphologies",
        ),
    ],
)
def test_memodel_with_synapses_validates_circuit_metadata(circuit, message):
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = circuit

    with pytest.raises(ValueError, match=message):
        memodel_with_synapses_section_type_options(client, uuid4())

    client.select_assets.assert_not_called()


def test_memodel_with_synapses_requires_sonata_asset():
    circuit_id = uuid4()
    circuit = Circuit.model_construct(
        id=circuit_id,
        scale=CircuitScale.single,
        number_neurons=1,
        has_morphologies=True,
    )
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = circuit
    client.select_assets.return_value.one.side_effect = EntitySDKError("not found")

    with pytest.raises(ValueError, match="missing a SONATA circuit asset"):
        memodel_with_synapses_section_type_options(client, circuit_id)


def test_memodel_with_synapses_sonata_asset_requires_id():
    circuit_id = uuid4()
    circuit = Circuit.model_construct(
        id=circuit_id,
        scale=CircuitScale.single,
        number_neurons=1,
        has_morphologies=True,
    )
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = circuit
    client.select_assets.return_value.one.return_value = MagicMock(id=None)

    with pytest.raises(ValueError, match="SONATA circuit asset is missing an id"):
        memodel_with_synapses_section_type_options(client, circuit_id)


@patch(f"{SERVICE_MODULE}.get_nodes", return_value=[])
@patch(f"{SERVICE_MODULE}.download_circuit_config")
def test_memodel_with_synapses_requires_one_biophysical_node(mock_download, mock_nodes):
    circuit_id = uuid4()
    circuit = Circuit.model_construct(
        id=circuit_id,
        scale=CircuitScale.single,
        number_neurons=1,
        has_morphologies=True,
    )
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = circuit
    client.select_assets.return_value.one.return_value = MagicMock(id=uuid4())

    with pytest.raises(ValueError, match="must contain one biophysical neuron"):
        memodel_with_synapses_section_type_options(client, circuit_id)

    mock_download.assert_called_once()
    mock_nodes.assert_called_once()


@patch(f"{SERVICE_MODULE}._memodel_section_type_options")
def test_morphology_source_dispatches_to_memodel(mock_options):
    source_id = uuid4()
    memodel = MEModel.model_construct(id=source_id)
    expected = [MorphologySectionTypeOption(value=3, label="Basal dendrite")]
    mock_options.return_value = expected
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.side_effect = _entity_lookup({MEModel: memodel})

    assert morphology_source_section_type_options(client, source_id) == expected

    assert client.get_entity.call_args_list == [
        call(entity_id=source_id, entity_type=MEModel),
    ]
    mock_options.assert_called_once_with(client, memodel)


@patch(f"{SERVICE_MODULE}.section_type_options")
@patch(f"{SERVICE_MODULE}._load_cell_morphology")
def test_morphology_source_dispatches_to_cell_morphology(mock_load, mock_options):
    source_id = uuid4()
    morphology = CellMorphology.model_construct(id=source_id, assets=[])
    expected = [MorphologySectionTypeOption(value=2, label="Axon")]
    mock_options.return_value = expected
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.side_effect = _entity_lookup({CellMorphology: morphology})

    assert morphology_source_section_type_options(client, source_id) == expected

    mock_load.assert_called_once_with(client, morphology)
    mock_options.assert_called_once_with(mock_load.return_value)


@patch(f"{SERVICE_MODULE}._memodel_with_synapses_section_type_options")
def test_morphology_source_dispatches_to_memodel_with_synapses(mock_options):
    source_id = uuid4()
    circuit = Circuit.model_construct(
        id=source_id,
        scale=CircuitScale.single,
        number_neurons=1,
        has_morphologies=True,
    )
    expected = [MorphologySectionTypeOption(value=4, label="Apical dendrite")]
    mock_options.return_value = expected
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.side_effect = _entity_lookup({Circuit: circuit})

    assert morphology_source_section_type_options(client, source_id) == expected

    assert client.get_entity.call_args_list == [
        call(entity_id=source_id, entity_type=MEModel),
        call(entity_id=source_id, entity_type=CellMorphology),
        call(entity_id=source_id, entity_type=Circuit),
    ]
    mock_options.assert_called_once_with(client, circuit)


def test_morphology_source_rejects_unexpected_entity_type():
    source_id = uuid4()
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.return_value = object()

    with pytest.raises(EntitySDKError, match=rf"Entity {source_id} is not an MEModel"):
        morphology_source_section_type_options(client, source_id)

    assert client.get_entity.call_count == 3


def test_morphology_source_rejects_unsupported_entity():
    source_id = uuid4()
    client = MagicMock(entitysdk.client.Client)
    client.get_entity.side_effect = EntitySDKError("not found")

    with pytest.raises(
        EntitySDKError,
        match=rf"Entity {source_id} is not an MEModel, MEModel-with-synapses circuit",
    ):
        morphology_source_section_type_options(client, source_id)

    assert client.get_entity.call_args_list == [
        call(entity_id=source_id, entity_type=MEModel),
        call(entity_id=source_id, entity_type=CellMorphology),
        call(entity_id=source_id, entity_type=Circuit),
    ]
