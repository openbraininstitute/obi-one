"""Preview the locations a morphology-location block generates on one morphology."""

from uuid import UUID

import morphio
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, Circuit, MEModel

from app.services.circuit_visualization import (
    load_cell_morphology,
    load_memodel_morphology,
    load_single_neuron_circuit_morphology,
)
from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.library.compartment_sets import sample_morphology_locations


def resolve_morphology(client: Client, entity_id: UUID) -> morphio.Morphology:
    """Load the single morphology an entity identifies.

    Accepts the same entity types as the morphology-properties endpoint, except that a circuit
    must hold exactly one neuron: a preview is drawn against one rendered morphology, and a
    multi-neuron circuit does not identify which one without a node id.

    Args:
        client: entitycore client used to fetch and download the entity's assets.
        entity_id: An MEModel, cell morphology, or single-neuron circuit.

    Returns:
        The morphology, sections ordered as NEURON orders them, so a section id means the same
        branch here as in a materialized compartment set. Propagates ``ValueError`` from the
        loaders when the entity carries no usable morphology.

    Raises:
        EntitySDKError: If the id resolves to none of those entity types.
    """
    for entity_type in (MEModel, CellMorphology, Circuit):
        try:
            entity = client.get_entity(entity_id=entity_id, entity_type=entity_type)
        except EntitySDKError:
            continue

        if isinstance(entity, MEModel):
            return load_memodel_morphology(client, entity)
        if isinstance(entity, CellMorphology):
            return load_cell_morphology(client, entity)
        if isinstance(entity, Circuit):
            return load_single_neuron_circuit_morphology(client, entity)

    msg = f"Entity {entity_id} is not an MEModel, single-neuron circuit, or cell morphology."
    raise EntitySDKError(msg)


def preview_morphology_locations(
    client: Client,
    entity_id: UUID,
    locations_block: MorphologyLocationsBlock,
) -> list[tuple[int, float]]:
    """Evaluate a morphology-location block against the morphology an entity identifies.

    Args:
        client: entitycore client used to resolve the morphology.
        entity_id: An MEModel, cell morphology, or single-neuron circuit.
        locations_block: The block to evaluate. Parameter sweeps are rejected.

    Returns:
        `(section_id, offset)` per generated location, in generation order. Section ids are
        SONATA global ids, matching the ids the viewer receives per section.

        Propagates ``TypeError`` from ``enforce_no_multi_param`` if any parameter is still a
        sweep list. That check runs before the morphology is resolved, so an unusable request
        costs no asset download.
    """
    locations_block.enforce_no_multi_param()

    morphology = resolve_morphology(client, entity_id)
    return sample_morphology_locations(
        locations_block=locations_block,
        morphology=morphology,
    )
