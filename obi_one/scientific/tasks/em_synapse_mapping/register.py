import logging
from pathlib import Path

from entitysdk import Client
from entitysdk.models import EMDenseReconstructionDataset
from entitysdk.types import CircuitBuildCategory

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.tasks.em_synapse_mapping.publication_links import assemble_publication_links
from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import ResolvedNeuron
from obi_one.utils import circuit_registration

L = logging.getLogger(__name__)


def register_output(
    db_client: Client,
    circuit_path: Path,
    resolved_neurons: list[ResolvedNeuron],
    source_dataset: EMDenseReconstructionDataset,
    em_dataset: EMDataSetFromID,
    all_notices: list[str],
    total_internal: int,
    total_external: int,
) -> str:
    """Register the EM synapse mapping output as a circuit entity.

    Uses register_circuit to handle entity creation, count computation,
    folder upload, compression, and additional asset generation.
    """
    em_entity = em_dataset.entity(db_client)
    pt_root_ids = [rn.pt_root_id for rn in resolved_neurons]
    n_neurons = len(resolved_neurons)

    # Build circuit name and description
    if n_neurons == 1:
        name = f"Afferent-synaptome-{pt_root_ids[0]}"
        description = (
            f"Morphology skeleton with isolated spines and afferent synapses\n"
            f"    (Synaptome) of the neuron with pt_root_id {pt_root_ids[0]}\n"
            f"    in dataset {source_dataset.name}.\n"
        )
    else:
        name = f"Multi-synaptome-{'-'.join(str(p) for p in pt_root_ids[:3])}"
        description = (
            f"Multi-neuron synaptome circuit with {n_neurons} neurons "
            f"(pt_root_ids: {pt_root_ids}) from dataset {source_dataset.name}.\n"
            f"Internal synapses: {total_internal}, External synapses: {total_external}.\n"
        )

    description += "Used tables with the following notice texts:\n"
    unique_notices = list(dict.fromkeys(str(n) for n in all_notices))
    for notice in unique_notices:
        description += notice + "\n"

    # Get publication links
    publications = assemble_publication_links(db_client, em_entity, all_notices)  # ty:ignore[invalid-argument-type]

    # Register circuit (entity + assets + links)
    registered_circuit = circuit_registration.register_circuit(
        client=db_client,
        circuit_path=circuit_path,
        name=name,
        description=description,
        build_category=CircuitBuildCategory.em_reconstruction,
        brain_region=source_dataset.brain_region,  # ty:ignore[invalid-argument-type]
        subject=source_dataset.subject,  # ty:ignore[invalid-argument-type]
        experiment_date=source_dataset.experiment_date,
        license=em_entity.license,  # ty:ignore[unresolved-attribute]
        publications=publications,
    )

    L.info(f"Output registered as: {registered_circuit.id}")  # ty:ignore[unresolved-attribute]
    return str(registered_circuit.id)  # ty:ignore[unresolved-attribute]
