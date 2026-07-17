import tempfile
from pathlib import Path
from uuid import UUID

import morphio
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, Circuit, MEModel
from entitysdk.types import AssetLabel, CircuitScale, ContentType

from app.schemas.morphology_section_types import MorphologySectionTypeOption
from app.services.circuit_visualization import (
    download_circuit_config,
    get_morphology,
    get_nodes,
)

_SECTION_TYPE_LABELS = {
    morphio.SectionType.axon: "Axon",
    morphio.SectionType.basal_dendrite: "Basal dendrite",
    morphio.SectionType.apical_dendrite: "Apical dendrite",
}
_MORPHOLOGY_ASSET_TYPES = (
    (ContentType.application_swc, ".swc"),
    (ContentType.application_x_hdf5, ".h5"),
    (ContentType.application_asc, ".asc"),
)
_STATIC_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS = {
    CircuitScale.pair,
    CircuitScale.small,
    CircuitScale.microcircuit,
}
_SUPPORTED_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS = {
    CircuitScale.single,
    *_STATIC_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS,
}


def static_section_type_options() -> list[MorphologySectionTypeOption]:
    return [
        MorphologySectionTypeOption(value=int(section_type), label=label)
        for section_type, label in _SECTION_TYPE_LABELS.items()
    ]


def section_type_options(
    morphology: morphio.Morphology,
) -> list[MorphologySectionTypeOption]:
    present_types = {section.type for section in morphology.sections}
    return [
        MorphologySectionTypeOption(value=int(section_type), label=label)
        for section_type, label in _SECTION_TYPE_LABELS.items()
        if section_type in present_types
    ]


def _load_morphology_content(content: bytes, suffix: str) -> morphio.Morphology:
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        return morphio.Morphology(tmp.name, options=morphio.Option.nrn_order)


def _load_cell_morphology(client: Client, morphology: CellMorphology) -> morphio.Morphology:
    if morphology.id is None:
        msg = "Cell morphology is missing an id."
        raise ValueError(msg)

    assets = morphology.assets or []
    for content_type, suffix in _MORPHOLOGY_ASSET_TYPES:
        asset = next(
            (
                asset
                for asset in assets
                if asset.content_type == content_type and asset.label == AssetLabel.morphology
            ),
            None,
        )
        if asset is None:
            continue
        if asset.id is None:
            msg = "Morphology asset is missing an id."
            raise ValueError(msg)

        content = client.download_content(
            entity_id=morphology.id,
            entity_type=CellMorphology,
            asset_id=asset.id,
        )
        return _load_morphology_content(content, suffix)

    msg = "Cell morphology has no supported SWC, H5, or ASC asset."
    raise ValueError(msg)


def memodel_section_type_options(
    client: Client,
    memodel_id: UUID,
) -> list[MorphologySectionTypeOption]:
    memodel = client.get_entity(entity_id=memodel_id, entity_type=MEModel)
    return _memodel_section_type_options(client, memodel)


def _memodel_section_type_options(
    client: Client,
    memodel: MEModel,
) -> list[MorphologySectionTypeOption]:
    morphology = memodel.morphology
    if not (morphology.assets or []):
        if morphology.id is None:
            msg = "MEModel morphology is missing an id."
            raise ValueError(msg)
        morphology = client.get_entity(entity_id=morphology.id, entity_type=CellMorphology)
    return section_type_options(_load_cell_morphology(client, morphology))


def _sonata_circuit_asset_id(client: Client, circuit: Circuit) -> UUID:
    try:
        asset = client.select_assets(
            entity=circuit,
            selection={"label": AssetLabel.sonata_circuit},
        ).one()
    except EntitySDKError as exc:
        msg = "MEModel-with-synapses circuit is missing a SONATA circuit asset."
        raise ValueError(msg) from exc

    if asset.id is None:
        msg = "SONATA circuit asset is missing an id."
        raise ValueError(msg)
    return asset.id


def memodel_with_synapses_section_type_options(
    client: Client,
    circuit_id: UUID,
) -> list[MorphologySectionTypeOption]:
    circuit = client.get_entity(entity_id=circuit_id, entity_type=Circuit)
    return _memodel_with_synapses_section_type_options(client, circuit)


def _memodel_with_synapses_section_type_options(
    client: Client,
    circuit: Circuit,
) -> list[MorphologySectionTypeOption]:
    if circuit.scale != CircuitScale.single or circuit.number_neurons != 1:
        msg = "MEModel-with-synapses source must be a single-neuron circuit."
        raise ValueError(msg)
    if circuit.id is None:
        msg = "MEModel-with-synapses circuit is missing an id."
        raise ValueError(msg)
    if not circuit.has_morphologies:
        msg = "MEModel-with-synapses circuit has no morphologies."
        raise ValueError(msg)

    asset_id = _sonata_circuit_asset_id(client, circuit)
    with tempfile.TemporaryDirectory() as tmp_dir:
        parent_dir = Path(tmp_dir)
        config = download_circuit_config(client, circuit.id, asset_id, parent_dir)
        nodes = get_nodes(config, parent_dir, client, circuit.id, asset_id)
        if len(nodes) != 1:
            msg = "MEModel-with-synapses circuit must contain one biophysical neuron."
            raise ValueError(msg)

        node = nodes[0]
        morphology = get_morphology(
            parent_dir,
            client,
            circuit.id,
            asset_id,
            Path(node.morphology_file),
            node.morphology_name,
        )
        return section_type_options(morphology)


def _circuit_section_type_options(
    client: Client,
    circuit: Circuit,
) -> list[MorphologySectionTypeOption]:
    if circuit.scale not in _SUPPORTED_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS:
        msg = "Circuit morphology section-type options are only supported up to microcircuit scale."
        raise ValueError(msg)
    if circuit.scale in _STATIC_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS:
        return static_section_type_options()
    return _memodel_with_synapses_section_type_options(client, circuit)


def morphology_source_section_type_options(
    client: Client,
    source_id: UUID,
) -> list[MorphologySectionTypeOption]:
    for entity_type in (MEModel, CellMorphology, Circuit):
        try:
            entity = client.get_entity(entity_id=source_id, entity_type=entity_type)
        except EntitySDKError:
            continue

        if isinstance(entity, MEModel):
            return _memodel_section_type_options(client, entity)
        if isinstance(entity, CellMorphology):
            return section_type_options(_load_cell_morphology(client, entity))
        if isinstance(entity, Circuit):
            return _circuit_section_type_options(client, entity)

    msg = (
        f"Entity {source_id} is not an MEModel, MEModel-with-synapses circuit, or cell morphology."
    )
    raise EntitySDKError(msg)
