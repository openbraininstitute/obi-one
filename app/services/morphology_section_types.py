from uuid import UUID

import morphio
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, Circuit, MEModel
from entitysdk.types import CircuitScale

from app.schemas.morphology_section_types import MorphologySectionTypeOption
from app.services.circuit_visualization import (
    load_cell_morphology,
    load_memodel_morphology,
    load_single_neuron_circuit_morphology,
)

_SECTION_TYPE_LABELS = {
    morphio.SectionType.basal_dendrite: "Basal dendrite",
    morphio.SectionType.apical_dendrite: "Apical dendrite",
}
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
    return section_type_options(load_memodel_morphology(client, memodel))


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
    return section_type_options(load_single_neuron_circuit_morphology(client, circuit))


def _circuit_section_type_options(
    client: Client,
    circuit: Circuit,
) -> list[MorphologySectionTypeOption]:
    if circuit.scale not in _SUPPORTED_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS:
        msg = "Circuit morphology section-type options are only supported up to microcircuit scale."
        raise ValueError(msg)
    if not circuit.has_morphologies:
        msg = "Circuit has no morphologies."
        raise ValueError(msg)
    if circuit.scale in _STATIC_CIRCUIT_SCALE_SECTION_TYPE_OPTIONS:
        return static_section_type_options()
    return _memodel_with_synapses_section_type_options(client, circuit)


def morphology_section_type_options(
    client: Client,
    entity_id: UUID,
) -> list[MorphologySectionTypeOption]:
    for entity_type in (MEModel, CellMorphology, Circuit):
        try:
            entity = client.get_entity(entity_id=entity_id, entity_type=entity_type)
        except EntitySDKError:
            continue

        if isinstance(entity, MEModel):
            return _memodel_section_type_options(client, entity)
        if isinstance(entity, CellMorphology):
            return section_type_options(load_cell_morphology(client, entity))
        if isinstance(entity, Circuit):
            return _circuit_section_type_options(client, entity)

    msg = (
        f"Entity {entity_id} is not an MEModel, MEModel-with-synapses circuit, or cell morphology."
    )
    raise EntitySDKError(msg)
