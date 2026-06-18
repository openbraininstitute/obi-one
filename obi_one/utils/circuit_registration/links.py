"""Registration of linked entities (derivations, contributions, publications)."""

import logging

from entitysdk import Client, models
from entitysdk.types import DerivationType

L = logging.getLogger(__name__)


def register_derivation(
    client: Client,
    from_entity: models.Circuit | None,
    derivation_type: DerivationType | None,
    registered_circuit: models.Circuit | None,
    *,
    dry_run: bool,
) -> models.Derivation | None:
    """Register a derivation link between a parent and a derived circuit.

    Args:
        client: The entitycore SDK client.
        from_entity: The parent circuit entity (None to skip).
        derivation_type: The type of derivation (must be a valid DerivationType).
        registered_circuit: The derived circuit entity.
        dry_run: If True, perform validation only without registering.

    Returns:
        The registered derivation, or None if skipped or dry_run.
    """
    if from_entity is None:
        L.info("No derivation parent provided - skipping")
        return None

    if derivation_type is None:
        msg = "derivation_type is required when from_entity is provided!"
        raise ValueError(msg)

    if dry_run:
        L.info(f"Derivation '{derivation_type}': DRY RUN (not registered)")
        return None

    if registered_circuit is None:
        msg = "registered_circuit is required when dry_run is False!"
        raise ValueError(msg)

    derivation_model = models.Derivation(
        used=from_entity,
        generated=registered_circuit,
        derivation_type=derivation_type,
    )
    registered_derivation = client.register_entity(derivation_model)
    L.info(f"Derivation link '{derivation_type}' registered")
    return registered_derivation


def _contribution_exists(
    client: Client, contr_model: models.Contribution
) -> models.Contribution | None:
    """Check if a contribution already exists for the given entity/agent/role combination."""
    res = client.search_entity(
        entity_type=models.Contribution,
        query={"entity__id": contr_model.entity.id},  # ty:ignore[unresolved-attribute]
    ).all()
    for r in res:
        if (
            r.agent.pref_label == contr_model.agent.pref_label
            and r.agent.type == contr_model.agent.type
            and r.role.name == contr_model.role.name
        ):
            return r
    return None


def register_contributions(
    client: Client,
    contribution_dict: dict,
    registered_circuit: models.Circuit | None,
    *,
    dry_run: bool,
) -> list[models.Contribution]:
    """Register contributions for a circuit entity.

    Skips contributions that already exist (deduplication).

    Args:
        client: The entitycore SDK client.
        contribution_dict: Resolved contributions (from get_contributions).
        registered_circuit: The circuit entity.
        dry_run: If True, perform validation only without registering.

    Returns:
        List of newly registered contribution entities.
    """
    if dry_run:
        L.info(f"Contributions: {len(contribution_dict)} (DRY RUN)")
        return []

    if registered_circuit is None:
        msg = "registered_circuit is required when dry_run is False!"
        raise ValueError(msg)

    contributions_list = []
    for cdict in contribution_dict.values():
        contr_model = models.Contribution(
            agent=cdict["agent"], role=cdict["role"], entity=registered_circuit
        )
        existing = _contribution_exists(client, contr_model)
        if existing is None:
            registered_contr = client.register_entity(contr_model)
            contributions_list.append(registered_contr)
        else:
            L.warning(
                f"Contribution for agent '{cdict['agent'].pref_label}' already exists - skipping"
            )
    L.info(f"Contributions: {len(contributions_list)} registered")
    return contributions_list


def register_publication_links(
    client: Client,
    publication_dict: dict,
    registered_circuit: models.Circuit | None,
    *,
    dry_run: bool,
) -> list[models.ScientificArtifactPublicationLink]:
    """Register publication links for a circuit entity.

    Skips links that already exist (deduplication).

    Args:
        client: The entitycore SDK client.
        publication_dict: Resolved publications (from get_publications).
        registered_circuit: The circuit entity.
        dry_run: If True, perform validation only without registering.

    Returns:
        List of newly registered publication link entities.
    """
    if dry_run:
        L.info(f"Publication links: {len(publication_dict)} (DRY RUN)")
        return []

    if registered_circuit is None:
        msg = "registered_circuit is required when dry_run is False!"
        raise ValueError(msg)

    publications_list = []
    for pdict in publication_dict.values():
        publ_link_model = models.ScientificArtifactPublicationLink(
            publication=pdict["entity"],
            scientific_artifact=registered_circuit,
            publication_type=pdict["type"],
        )

        # Check if already registered
        res = client.search_entity(
            entity_type=models.ScientificArtifactPublicationLink,
            query={
                "publication__DOI": publ_link_model.publication.DOI,
                "scientific_artifact__id": publ_link_model.scientific_artifact.id,
                "publication_type": publ_link_model.publication_type,
            },
        ).all()
        if len(res) == 0:
            registered_link = client.register_entity(publ_link_model)
            publications_list.append(registered_link)
        else:
            L.warning(
                f"Publication link for DOI '{pdict['entity'].DOI}' already registered - skipping"
            )
    L.info(f"Publication links: {len(publications_list)} registered")
    return publications_list
