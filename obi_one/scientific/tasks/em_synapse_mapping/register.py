import logging
import os

from entitysdk import Client
from entitysdk.models import (
    Circuit,
    EMDenseReconstructionDataset,
    ScientificArtifactPublicationLink,
)
from entitysdk.schemas.asset import MultipartUploadTransferConfig
from entitysdk.types import (
    AssetLabel,
    CircuitBuildCategory,
    CircuitScale,
    ContentType,
    PublicationType,
)

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.tasks.em_synapse_mapping.publication_links import assemble_publication_links
from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import ResolvedNeuron

L = logging.getLogger(__name__)


def register_output(
    db_client: Client,
    resolved_neurons: list[ResolvedNeuron],
    source_dataset: EMDenseReconstructionDataset,
    em_dataset: EMDataSetFromID,
    all_notices: list[str],
    total_synapses: int,
    total_connections: int,
    total_internal: int,
    total_external: int,
    file_paths: dict[os.PathLike, os.PathLike],
    compressed_path: os.PathLike,
) -> str:
    em_entity = em_dataset.entity(db_client)
    pt_root_ids = [rn.pt_root_id for rn in resolved_neurons]
    n_neurons = len(resolved_neurons)

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

    circ_entity = Circuit(
        name=name,
        description=description,
        number_neurons=n_neurons,
        number_synapses=total_synapses,
        number_connections=total_connections,
        scale=CircuitScale.small if n_neurons > 1 else CircuitScale.single,
        build_category=CircuitBuildCategory.em_reconstruction,
        subject=source_dataset.subject,
        has_morphologies=True,
        has_electrical_cell_models=any(rn.use_me_model for rn in resolved_neurons),
        has_spines=True,
        brain_region=source_dataset.brain_region,
        experiment_date=source_dataset.experiment_date,
        license=em_entity.license,  # ty:ignore[unresolved-attribute]
    )
    existing_circuit = db_client.register_entity(circ_entity)

    db_client.upload_directory(
        entity_id=existing_circuit.id,  # ty:ignore[invalid-argument-type]
        entity_type=Circuit,
        name="sonata_synaptome",
        paths=file_paths,
        label=AssetLabel.sonata_circuit,
    )

    db_client.upload_file(
        entity_id=existing_circuit.id,  # ty:ignore[invalid-argument-type]
        entity_type=Circuit,
        file_path=compressed_path,
        file_content_type=ContentType.application_gzip,
        asset_label=AssetLabel.compressed_sonata_circuit,
        transfer_config=MultipartUploadTransferConfig(),
    )

    for publication in assemble_publication_links(db_client, em_entity, all_notices):  # ty:ignore[invalid-argument-type]
        new_link = ScientificArtifactPublicationLink(
            scientific_artifact=existing_circuit,
            publication=publication,
            publication_type=PublicationType.component_source,
        )
        db_client.register_entity(new_link)
    L.info(f"Output registered as: {existing_circuit.id}")
    return str(existing_circuit.id)
