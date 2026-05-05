import logging

from entitysdk import Client
from entitysdk.models import (
    EMDenseReconstructionDataset,
    Publication,
    ScientificArtifactPublicationLink,
)
from entitysdk.types import PublicationType

L = logging.getLogger(__name__)


def assemble_publication_links(
    db_client: Client,
    em_dataset: EMDenseReconstructionDataset,
    lst_notices: list[str],  # NOQA: ARG001
) -> list[Publication]:
    src_links = db_client.search_entity(
        entity_type=ScientificArtifactPublicationLink,
        query={"scientific_artifact__id": em_dataset.id},
    ).all()
    src_pubs = [
        x.publication for x in src_links if x.publication_type != PublicationType.application
    ]
    # TODO: Parse DOIs out of the lst_notices. Create publications for them.
    return src_pubs
