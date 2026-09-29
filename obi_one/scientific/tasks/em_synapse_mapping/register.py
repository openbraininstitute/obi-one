import logging
from pathlib import Path

from entitysdk import Client
from entitysdk.models import EMDenseReconstructionDataset
from entitysdk.types import CircuitBuildCategory, TargetSimulator

from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.tasks.em_synapse_mapping.publication_links import assemble_publication_links
from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import ResolvedNeuron

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
    target_simulator: TargetSimulator = TargetSimulator.NEURON,
    *,
    async_validation: bool = False,
) -> str:
    """Register EM synapse mapping output as circuit entity.

    Delegates to ``register_circuit``: entity, counts, folder upload, extra assets.

    Args:
        db_client: EntitySDK client.
        circuit_path: Path to output circuit_config.json.
        resolved_neurons: Mapped neurons; set name and description.
        source_dataset: Source EM dense reconstruction dataset.
        em_dataset: EM dataset reference; gives license and publications.
        all_notices: CAVE table notice texts, appended to description.
        total_internal: Internal synapse count (multi-neuron description).
        total_external: External synapse count (multi-neuron description).
        target_simulator: Target simulator of circuit.
        async_validation: Register as draft, validated later by launch-system job.
            See ``register_circuit``.

    Returns:
        Registered circuit ID.
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
        target_simulator=target_simulator,
        experiment_date=source_dataset.experiment_date,
        license=em_entity.license,  # ty:ignore[unresolved-attribute]
        publications=publications,
        skip_additional_assets=False,
        skip_validation=True,
        async_validation=async_validation,
    )

    L.info(f"Output registered as: {registered_circuit.id}")  # ty:ignore[unresolved-attribute]
    return str(registered_circuit.id)  # ty:ignore[unresolved-attribute]
