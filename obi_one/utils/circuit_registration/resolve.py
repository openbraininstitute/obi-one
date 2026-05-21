"""Entity resolution helpers for circuit registration."""

import logging
from datetime import datetime

from entitysdk import Client, models, types
from entitysdk.types import DerivationType

L = logging.getLogger(__name__)


def get_circuit(
    client: Client, circuit_name: str | None, *, must_exist: bool = False
) -> models.Circuit | None:
    """Search for a circuit entity by name.

    Args:
        client: The entitycore SDK client.
        circuit_name: Name of the circuit to search for.
        must_exist: If True, raise an error when the circuit is not found.

    Returns:
        The circuit entity if found, None otherwise.
    """
    if circuit_name is None:
        return None

    res = client.search_entity(entity_type=models.Circuit, query={"name": circuit_name}).all()
    if len(res) == 0:
        if must_exist:
            msg = f"Circuit '{circuit_name}' not found!"
            raise ValueError(msg)
        return None

    for c in res:
        L.info(f"Circuit '{circuit_name}' found under ID {c.id}")
    if len(res) == 1:
        return res[0]

    msg = f"Multiple circuits with name '{circuit_name}' found!"
    raise ValueError(msg)


def check_if_circuit_exists(client: Client, circuit_metadata: dict) -> None:
    """Check that a circuit with the given name does not already exist.

    Raises ValueError if the circuit name is missing or already registered.
    """
    circuit_name = circuit_metadata.get("name")
    if circuit_name is None:
        msg = "Circuit name missing!"
        raise ValueError(msg)
    if get_circuit(client, circuit_name, must_exist=False) is not None:
        msg = f"Circuit '{circuit_name}' already exists!"
        raise ValueError(msg)
    L.info(f"Circuit '{circuit_name}' not yet registered.")


def get_root_circuit(client: Client, circuit_metadata: dict) -> models.Circuit | None:
    """Resolve the root circuit entity from metadata.

    Returns:
        The root circuit entity, or None if not specified.
    """
    root_name = circuit_metadata.get("root")
    root = get_circuit(client, root_name, must_exist=True)
    if root is None:
        L.info("No root circuit specified")
    else:
        L.info(f"Root circuit: {root.name} (ID {root.id})")
    return root


def get_parent_circuit(client: Client, circuit_metadata: dict) -> models.Circuit | None:
    """Resolve the parent circuit entity from metadata.

    Validates that a derivation type is provided when a parent exists,
    and that the derivation type is valid.

    Returns:
        The parent circuit entity, or None if not specified.
    """
    parent_name = circuit_metadata.get("parent")
    parent = get_circuit(client, parent_name, must_exist=True)
    if parent is None:
        L.info("No parent circuit specified")
        if circuit_metadata["derivation_type"] is not None:
            msg = (
                f"Derivation type '{circuit_metadata['derivation_type']}'"
                " requires a parent circuit!"
            )
            raise ValueError(msg)
    else:
        L.info(f"Parent circuit: {parent.name} (ID {parent.id})")
        valid_derivation_types = [str(dtype) for dtype in DerivationType]
        if circuit_metadata["derivation_type"] not in valid_derivation_types:
            msg = f"A valid derivation type is required (valid: {valid_derivation_types})!"
            raise ValueError(msg)
    return parent


def get_exp_date(circuit_metadata: dict) -> datetime | None:
    """Parse experiment date from metadata.

    Supports formats: '%d.%m.%Y' and '%B, %Y'.

    Returns:
        Parsed datetime or None if not specified.
    """
    exp_date_str = circuit_metadata.get("experiment_date")
    if exp_date_str is None:
        return None

    for fmt in ("%d.%m.%Y", "%B, %Y"):
        try:
            exp_date = datetime.strptime(exp_date_str, fmt)  # noqa: DTZ007
        except ValueError:
            continue
        L.info(f"Experiment date: {exp_date}")
        return exp_date

    msg = f"Date format '{exp_date_str}' not supported!"
    raise ValueError(msg)


def find_agent(
    client: Client, agent_name: str, agent_type: str
) -> models.Consortium | models.Organization | models.Person:
    """Find an agent (person, organization, or consortium) by name.

    Args:
        client: The entitycore SDK client.
        agent_name: Preferred label of the agent.
        agent_type: Type of agent ('person', 'organization', or 'consortium').

    Returns:
        The agent entity.
    """
    entity_type = getattr(models, agent_type.title())
    agents = client.search_entity(entity_type=entity_type, query={"pref_label": agent_name}).all()
    if len(agents) == 0:
        msg = f"{agent_type.title()} '{agent_name}' not found!"
        raise ValueError(msg)
    if len(agents) > 1:
        L.warning(
            f"{agent_type.title()} '{agent_name}' found multiple times - using first instance"
        )
    return agents[0]


def find_role(client: Client, role_name: str) -> models.Role:
    """Find a role entity by name.

    Args:
        client: The entitycore SDK client.
        role_name: Name of the role to find.

    Returns:
        The role entity.
    """
    all_roles = client.search_entity(entity_type=models.Role).all()
    matches = [role for role in all_roles if role.name == role_name]
    if len(matches) != 1:
        msg = f"Role '{role_name}' not found or multiple entities exist!"
        raise ValueError(msg)
    return matches[0]


def get_contributions(
    client: Client, circuit_contributions: dict, *, verbose: bool = False
) -> dict:
    """Resolve contribution agents and roles from a contributions dictionary.

    Args:
        client: The entitycore SDK client.
        circuit_contributions: Mapping of contributor name to dict with 'type' and 'role'.
        verbose: If True, log details for each contributor.

    Returns:
        Dictionary mapping contributor name to resolved {'agent', 'role'} entities.
    """
    contr_entities = {}
    contr_counts: dict[str, int] = {}
    for cname, cdict in circuit_contributions.items():
        agent = find_agent(client, cname, cdict.get("type"))
        role = find_role(client, cdict.get("role"))
        contr_entities[cname] = {"agent": agent, "role": role}
        if verbose:
            L.info(
                f"Contributing {agent.type} '{agent.pref_label}' (ID {agent.id}) "
                f"with role '{role.name}' (ID {role.id})"
            )
        contr_counts[agent.type.title()] = contr_counts.get(agent.type.title(), 0) + 1
    L.info(f"Contributors: {contr_counts}")
    return contr_entities


def get_publications(client: Client, circuit_publications: dict, *, verbose: bool = False) -> dict:
    """Resolve publication entities from a publications dictionary.

    Args:
        client: The entitycore SDK client.
        circuit_publications: Mapping of DOI to dict with 'type' (publication type).
        verbose: If True, log details for each publication.

    Returns:
        Dictionary mapping DOI to resolved {'entity', 'type'}.
    """
    publ_entities = {}
    publ_counts: dict[str, int] = {}
    for doi, type_dict in circuit_publications.items():
        publ_type = type_dict.get("type")
        if publ_type not in types.PublicationType:
            msg = f"Publication type '{publ_type}' unknown!"
            raise ValueError(msg)

        res = client.search_entity(entity_type=models.Publication, query={"DOI": doi}).all()
        if len(res) == 0:
            msg = (
                f"Publication with DOI {doi} not found!"
                " The publication needs to be registered first."
            )
            raise ValueError(msg)
        if len(res) > 1:
            msg = f"Publication with DOI {doi} found multiple times!"
            raise ValueError(msg)
        publ = res[0]
        publ_entities[doi] = {"entity": publ, "type": publ_type}
        if verbose:
            L.info(f"Publication {doi} (ID {publ.id}) of type '{publ_type}'")
        publ_counts[publ_type.title()] = publ_counts.get(publ_type.title(), 0) + 1
    L.info(f"Publications: {publ_counts}")
    return publ_entities


def get_subject(client: Client, circuit_metadata: dict) -> models.Subject:
    """Resolve the subject entity from metadata and validate species consistency."""
    subj_name = circuit_metadata.get("subject")
    if subj_name is None:
        msg = "Subject must be provided!"
        raise ValueError(msg)
    subject = client.search_entity(entity_type=models.Subject, query={"name": subj_name}).all()
    if len(subject) == 0:
        msg = f"Subject '{subj_name}' not found! Subjects need to be registered beforehand."
        raise ValueError(msg)
    if len(subject) > 1:
        msg = f"Multiple subject entities with name '{subj_name}' found!"
        raise ValueError(msg)
    subject = subject[0]
    L.info(f"Subject '{subject.name}' (ID {subject.id})")

    species_name = circuit_metadata.get("species")
    if subject.species.name != species_name:
        msg = f"Subject '{subject.name}' and species '{species_name}' are inconsistent!"
        raise ValueError(msg)

    return subject


def get_brain_region_hierarchy(
    client: Client, circuit_metadata: dict
) -> models.BrainRegionHierarchy:
    """Resolve the brain region hierarchy entity from metadata."""
    hierarchy_name = circuit_metadata.get("brain_region_hierarchy")
    if hierarchy_name is None:
        msg = "Brain region hierarchy must be provided!"
        raise ValueError(msg)
    brain_hierarchy = client.search_entity(
        entity_type=models.BrainRegionHierarchy, query={"name": hierarchy_name}
    ).all()
    if len(brain_hierarchy) == 0:
        msg = (
            f"Brain region hierarchy '{hierarchy_name}' not found!"
            " Brain hierarchies need to be registered beforehand."
        )
        raise ValueError(msg)
    if len(brain_hierarchy) > 1:
        msg = f"Multiple brain region hierarchies with name '{hierarchy_name}' found!"
        raise ValueError(msg)
    brain_hierarchy = brain_hierarchy[0]
    L.info(f"Brain region hierarchy '{brain_hierarchy.name}' (ID {brain_hierarchy.id})")
    return brain_hierarchy


def check_hierarchy_species(
    brain_hierarchy: models.BrainRegionHierarchy, subject: models.Subject
) -> None:
    """Check that brain region hierarchy is consistent with given species."""
    if brain_hierarchy.species.id != subject.species.id:
        msg = (
            f"Species mismatch for brain region hierarchy '{brain_hierarchy.name}'"
            f" ('{brain_hierarchy.species.name}'),"
            f" should belong to '{subject.species.name}'!"
        )
        raise ValueError(msg)


def get_brain_region(
    client: Client, circuit_metadata: dict, brain_hierarchy: models.BrainRegionHierarchy
) -> models.BrainRegion:
    """Resolve the brain region entity from metadata within hierarchy."""
    region_name = circuit_metadata.get("brain_region")
    if region_name is None:
        msg = "Brain region must be provided!"
        raise ValueError(msg)
    brain_region = client.search_entity(
        entity_type=models.BrainRegion,
        query={"name": region_name, "hierarchy_id": brain_hierarchy.id},
    ).all()
    if len(brain_region) == 0:
        msg = (
            f"Brain region '{region_name}' not found in hierarchy '{brain_hierarchy.name}'!"
            " Brain regions need to be registered beforehand."
        )
        raise ValueError(msg)
    if len(brain_region) > 1:
        msg = (
            f"Multiple brain regions with name '{region_name}'"
            f" found in hierarchy '{brain_hierarchy.name}'!"
        )
        raise ValueError(msg)
    brain_region = brain_region[0]
    L.info(f"Brain region '{brain_region.name}' (ID {brain_region.id})")
    return brain_region


def get_license(client: Client, circuit_metadata: dict) -> models.License | None:
    """Resolve the license entity from metadata."""
    lic_name = circuit_metadata.get("license")
    if lic_name is None:
        L.warning("No license specified!")
        return None

    license_results = client.search_entity(
        entity_type=models.License, query={"label": lic_name}
    ).all()
    if len(license_results) == 0:
        msg = f"License '{lic_name}' not found! Licenses need to be registered beforehand."
        raise ValueError(msg)
    if len(license_results) > 1:
        msg = f"Multiple licenses with label '{lic_name}' found!"
        raise ValueError(msg)
    license_entity = license_results[0]
    L.info(f"License '{license_entity.label}' {license_entity.name} (ID {license_entity.id})")
    return license_entity
