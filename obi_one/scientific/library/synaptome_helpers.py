import logging
import tarfile
from pathlib import Path

from entitysdk import Client
from entitysdk.models import Circuit, Publication, ScientificArtifactPublicationLink
from entitysdk.models.scientific_artifact import ScientificArtifact
from entitysdk.types import (
    AssetLabel,
    CircuitBuildCategory,
    CircuitScale,
    ContentType,
    PublicationType,
)

L = logging.getLogger(__name__)


def compress_output(out_root: Path) -> Path:
    output_file = out_root / "circuit.gz"
    if Path(output_file).exists():
        msg = f"Output file '{output_file}' already exists!"
        raise ValueError(msg)
    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(
            out_root,
            arcname=output_file.stem,
        )
    return output_file


def assemble_publication_links(
    db_client: Client,
    scientific_artifact: ScientificArtifact,
    lst_notices: list[str],  # NOQA: ARG001
) -> list[Publication]:
    src_links = db_client.search_entity(
        entity_type=ScientificArtifactPublicationLink,
        query={"scientific_artifact__id": scientific_artifact.id},
    ).all()
    src_pubs = [
        _x.publication for _x in src_links if _x.publication_type != PublicationType.application
    ]
    # TODO: Parse DOIs out of the lst_notices. Create publications for them.
    return src_pubs


def synaptome_name(pt_root_id: int) -> str:
    name = f"Afferent-synaptome-{pt_root_id}"
    return name


def synaptome_name_with_physiology(name: str) -> str:
    name += "-with-physiology"
    return name


def synaptome_description(
    pt_root_id: int, source_dataset: ScientificArtifact, lst_notices: list[str]
) -> str:
    description = f"""Morphology skeleton with isolated spines and afferent synapses
    (Synaptome) of the neuron with pt_root_id {pt_root_id}
    in dataset {source_dataset.name}.\n"""
    description += "Used tables with the following notice texts:\n"
    for notice in lst_notices:
        description += str(notice) + "\n"
    return description


def synaptome_description_with_physiology(description: str) -> str:
    """Split description at first sentence and mention physiology."""
    for sep in [".\n", ". ", "."]:
        parts = description.split(sep)
        if len(parts) > 1:
            break
    new_parts = [parts[0] + ", with physiological parameterization of the synapses", *parts[1:]]
    description = sep.join(new_parts)
    return description


def register_synaptome(
    db_client: Client,
    name: str,
    description: str,
    number_synapses: int,
    number_connections: int,
    source_dataset: ScientificArtifact,
    em_dataset: ScientificArtifact,
    lst_notices: list[str],
    file_paths: dict[str, Path],
    compressed_path: Path,
) -> Circuit:
    license = em_dataset.license

    circ_entity = Circuit(
        name=name,
        description=description,
        number_neurons=1,
        number_synapses=number_synapses,
        number_connections=number_connections,
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
    return existing_circuit
