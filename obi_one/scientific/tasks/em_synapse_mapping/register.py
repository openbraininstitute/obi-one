import logging
import os

import pandas  # NOQA: ICN001
from entitysdk import Client
from entitysdk._server_schemas import (
    AssetLabel,  # NOQA: PLC2701
    CircuitBuildCategory,  # NOQA: PLC2701
    CircuitScale,  # NOQA: PLC2701
    ContentType,  # NOQA: PLC2701
    PublicationType,  # NOQA: PLC2701
)
from entitysdk.models import (
    Circuit,
    EMCellMesh,
    EMDenseReconstructionDataset,
    ScientificArtifactPublicationLink,
)
from entitysdk.schemas.asset import MultipartUploadTransferConfig

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.tasks.em_synapse_mapping.publication_links import assemble_publication_links

L = logging.getLogger(__name__)


def register_output_single(
    db_client: Client,
    pt_root_id: int,
    mapped_synapses_df: pandas.DataFrame,
    syn_pre_post_df: pandas.DataFrame,
    source_dataset: EMCellMesh,
    em_dataset: EMDenseReconstructionDataset,
    lst_notices: list[str],
    file_paths: dict[os.PathLike, os.PathLike],
    compressed_path: os.PathLike,
) -> str:
    license = em_dataset.license
    description = f"""Morphology skeleton with isolated spines and afferent synapses
    (Synaptome) of the neuron with pt_root_id {pt_root_id}
    in dataset {source_dataset.name}.\n"""
    description += "Used tables with the following notice texts:\n"
    for notice in lst_notices:
        description += str(notice) + "\n"

    circ_entity = Circuit(
        name=f"Afferent-synaptome-{pt_root_id}",
        description=description,
        number_neurons=1,
        number_synapses=len(mapped_synapses_df),
        number_connections=len(syn_pre_post_df["pre_node_id"].drop_duplicates()),
        scale=CircuitScale.single,
        build_category=CircuitBuildCategory.em_reconstruction,
        subject=source_dataset.subject,
        has_morphologies=True,
        has_electrical_cell_models=False,
        has_spines=True,
        brain_region=source_dataset.brain_region,
        experiment_date=source_dataset.experiment_date,
        license=license,
    )
    existing_circuit = db_client.register_entity(circ_entity)

    db_client.upload_directory(
        entity_id=existing_circuit.id,
        entity_type=Circuit,
        name="sonata_synaptome",
        paths=file_paths,
        label=AssetLabel.sonata_circuit,
    )

    db_client.upload_file(
        entity_id=existing_circuit.id,
        entity_type=Circuit,
        file_path=compressed_path,
        file_content_type=ContentType.application_gzip,
        asset_label=AssetLabel.compressed_sonata_circuit,
    )

    for publication in assemble_publication_links(db_client, em_dataset, lst_notices):
        new_link = ScientificArtifactPublicationLink(
            scientific_artifact=existing_circuit,
            publication=publication,
            publication_type=PublicationType.component_source,
        )
        db_client.register_entity(new_link)
    L.info(f"Output registered as: {existing_circuit.id}")

    return str(existing_circuit.id)


def register_output_multiple(
    db_client: Client,
    resolved_neurons: list,
    source_dataset: EMDenseReconstructionDataset,
    em_dataset: EMDataSetFromID,
    all_notices: list[str],
    total_synapses: int,
    total_internal: int,
    total_external: int,
    file_paths: dict[os.PathLike, os.PathLike],
    compressed_path: os.PathLike,
) -> None:
    em_entity = em_dataset.entity(db_client)
    pt_root_ids = [rn.pt_root_id for rn in resolved_neurons]
    n_neurons = len(resolved_neurons)

    description = (
        f"Multi-neuron synaptome circuit with {n_neurons} neurons "
        f"(pt_root_ids: {pt_root_ids}) from dataset {source_dataset.name}.\n"
        f"Internal connections: {total_internal}, External inputs: {total_external}.\n"
    )
    description += "Used tables with the following notice texts:\n"
    unique_notices = list(dict.fromkeys(str(n) for n in all_notices))
    for notice in unique_notices:
        description += notice + "\n"

    circ_entity = Circuit(
        name=f"Multi-synaptome-{'-'.join(str(p) for p in pt_root_ids[:3])}",
        description=description,
        number_neurons=n_neurons,
        number_synapses=total_synapses,
        number_connections=total_internal + total_external,
        scale=CircuitScale.small if n_neurons > 1 else CircuitScale.single,
        build_category=CircuitBuildCategory.em_reconstruction,
        subject=source_dataset.subject,
        has_morphologies=True,
        has_electrical_cell_models=any(rn.use_me_model for rn in resolved_neurons),
        has_spines=True,
        brain_region=source_dataset.brain_region,
        experiment_date=source_dataset.experiment_date,
        license=em_entity.license,
    )
    existing_circuit = db_client.register_entity(circ_entity)

    db_client.upload_directory(
        entity_id=existing_circuit.id,
        entity_type=Circuit,
        name="sonata_synaptome",
        paths=file_paths,
        label=AssetLabel.sonata_circuit,
    )

    db_client.upload_file(
        entity_id=existing_circuit.id,
        entity_type=Circuit,
        file_path=compressed_path,
        file_content_type=ContentType.application_gzip,
        asset_label=AssetLabel.compressed_sonata_circuit,
        transfer_config=MultipartUploadTransferConfig(),
    )

    for publication in assemble_publication_links(db_client, em_entity, all_notices):
        new_link = ScientificArtifactPublicationLink(
            scientific_artifact=existing_circuit,
            publication=publication,
            publication_type=PublicationType.component_source,
        )
        db_client.register_entity(new_link)
    L.info(f"Output registered as: {existing_circuit.id}")
    return existing_circuit.id
