"""Utilities for registering circuit entities to entitycore."""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import UUID

import numpy as np
from entitysdk import Client, models, types
from entitysdk.types import DerivationType

from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.utils.circuit import get_circuit_properties, get_circuit_size

L = logging.getLogger(__name__)

AWS_S3_ROOT = "s3://openbluebrain"


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

    res = client.search_entity(
        entity_type=models.Circuit, query={"name": circuit_name}
    ).all()
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
            msg = f"Derivation type '{circuit_metadata['derivation_type']}' requires a parent circuit!"
            raise ValueError(msg)
    else:
        L.info(f"Parent circuit: {parent.name} (ID {parent.id})")
        valid_derivation_types = [str(_dtype) for _dtype in DerivationType]
        if circuit_metadata["derivation_type"] not in valid_derivation_types:
            msg = f"A valid derivation type is required (valid: {valid_derivation_types})!"
            raise ValueError(msg)
    return parent


def check_counts(circuit_metadata: dict) -> None:
    """Validate neuron/synapse/connection counts and circuit scale consistency."""
    nnrn = circuit_metadata.get("number_neurons", 0)
    if nnrn <= 0:
        msg = "Valid number of neurons required!"
        raise ValueError(msg)
    nsyn = circuit_metadata.get("number_synapses", 0)
    if nsyn <= 0:
        msg = "Valid number of synapses required!"
        raise ValueError(msg)
    nconn = circuit_metadata.get("number_connections")
    if nconn is not None and nconn <= 0:
        msg = "Valid number of connections required (or None to skip)!"
        raise ValueError(msg)

    scale = circuit_metadata["scale"]
    if (
        (nnrn == 1 and scale != "single")
        or (nnrn == 2 and scale != "pair")
        or (nnrn > 2 and nnrn <= 20 and scale != "small")
        or (
            nnrn > 20
            and scale not in ["microcircuit", "region", "system", "whole_brain"]
        )
    ):
        msg = f"Number of neurons ({nnrn}) does not match circuit scale '{scale}'!"
        raise ValueError(msg)
    L.info(f"#Neurons: {nnrn}, #Synapses: {nsyn}, #Connections: {nconn}, Scale: {scale}")


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
    agents = client.search_entity(
        entity_type=entity_type, query={"pref_label": agent_name}
    ).all()
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
    matches = [_role for _role in all_roles if _role.name == role_name]
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


def get_publications(
    client: Client, circuit_publications: dict, *, verbose: bool = False
) -> dict:
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
        # Get publication type
        publ_type = type_dict.get("type")
        if publ_type not in types.PublicationType:
            msg = f"Publication type '{publ_type}' unknown!"
            raise ValueError(msg)

        # Get publication entity
        res = client.search_entity(
            entity_type=models.Publication, query={"DOI": doi}
        ).all()
        if len(res) == 0:
            msg = f"Publication with DOI {doi} not found! The publication needs to be registered first."
            raise ValueError(msg)
        elif len(res) > 1:
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
    """Resolve the subject entity from metadata and validate species consistency.

    Args:
        client: The entitycore SDK client.
        circuit_metadata: Dictionary containing 'subject' and 'species' keys.

    Returns:
        The subject entity.
    """
    subj_name = circuit_metadata.get("subject")
    if subj_name is None:
        msg = "Subject must be provided!"
        raise ValueError(msg)
    subject = client.search_entity(
        entity_type=models.Subject, query={"name": subj_name}
    ).all()
    if len(subject) == 0:
        msg = f"Subject '{subj_name}' not found! Subjects need to be registered beforehand."
        raise ValueError(msg)
    if len(subject) > 1:
        msg = f"Multiple subject entities with name '{subj_name}' found!"
        raise ValueError(msg)
    subject = subject[0]
    L.info(f"Subject '{subject.name}' (ID {subject.id})")

    # Check consistency with species
    species_name = circuit_metadata.get("species")
    if subject.species.name != species_name:
        msg = f"Subject '{subject.name}' and species '{species_name}' are inconsistent!"
        raise ValueError(msg)

    return subject


def get_brain_region(client: Client, circuit_metadata: dict) -> models.BrainRegion:
    """Resolve the brain region entity from metadata.

    Args:
        client: The entitycore SDK client.
        circuit_metadata: Dictionary containing 'brain_region' key.

    Returns:
        The brain region entity.
    """
    region_name = circuit_metadata.get("brain_region")
    if region_name is None:
        msg = "Brain region must be provided!"
        raise ValueError(msg)
    brain_region = client.search_entity(
        entity_type=models.BrainRegion, query={"name": region_name}
    ).all()
    if len(brain_region) == 0:
        msg = f"Brain region '{region_name}' not found! Brain regions need to be registered beforehand."
        raise ValueError(msg)
    if len(brain_region) > 1:
        msg = f"Multiple brain regions with name '{region_name}' found!"
        raise ValueError(msg)
    brain_region = brain_region[0]
    L.info(f"Brain region '{brain_region.name}' (ID {brain_region.id})")
    return brain_region


def get_license(client: Client, circuit_metadata: dict) -> models.License | None:
    """Resolve the license entity from metadata.

    Args:
        client: The entitycore SDK client.
        circuit_metadata: Dictionary containing 'license' key.

    Returns:
        The license entity, or None if not specified.
    """
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


def register_circuit_entity(
    client: Client,
    circuit_metadata: dict,
    subject: models.Subject,
    brain_region: models.BrainRegion,
    license: models.License | None,
    root: models.Circuit | None,
    exp_date: datetime | None,
    *,
    make_public: bool,
    check_only: bool,
) -> models.Circuit | None:
    """Register a new circuit entity to entitycore.

    Args:
        client: The entitycore SDK client.
        circuit_metadata: Dictionary with circuit properties (name, description, counts, etc.).
        subject: The subject entity.
        brain_region: The brain region entity.
        license: The license entity (or None).
        root: The root circuit entity (or None).
        exp_date: The experiment date (or None).
        make_public: Whether to make the circuit publicly accessible.
        check_only: If True, perform a dry run without registering.

    Returns:
        The registered circuit entity, or None if check_only is True.
    """
    circuit_model = models.Circuit(
        name=circuit_metadata["name"],
        description=circuit_metadata["description"],
        subject=subject,
        brain_region=brain_region,
        license=license,
        number_neurons=circuit_metadata["number_neurons"],
        number_synapses=circuit_metadata["number_synapses"],
        number_connections=circuit_metadata.get("number_connections"),
        has_morphologies=circuit_metadata["has_morphologies"],
        has_point_neurons=circuit_metadata["has_point_neurons"],
        has_electrical_cell_models=circuit_metadata["has_electrical_cell_models"],
        has_spines=circuit_metadata["has_spines"],
        scale=circuit_metadata["scale"],
        build_category=circuit_metadata["build_category"],
        root_circuit_id=None if root is None else root.id,
        atlas_id=None,  # TODO: Not yet implemented
        contact_email=circuit_metadata.get("contact"),
        published_in=circuit_metadata.get("published_in"),
        experiment_date=exp_date,
        authorized_public=make_public,
    )

    if check_only:
        L.info(f"Circuit entity '{circuit_model.name}': CHECK ONLY (not registered)")
        return None

    registered_circuit = client.register_entity(circuit_model)
    L.info(f"Circuit '{registered_circuit.name}' registered under ID {registered_circuit.id}")
    return registered_circuit


# --- Asset validation and registration ---


def _is_on_aws_s3(file_path: str) -> bool:
    """Check if a file path points to an AWS S3 Open Data location."""
    return file_path.lower().startswith(AWS_S3_ROOT)


def _check_file_path(file_path: str) -> None:
    """Validate that a file path exists (locally or on AWS S3).

    Raises ValueError if the path is empty or does not exist.
    """
    if len(file_path) == 0:
        msg = "File path missing!"
        raise ValueError(msg)

    if _is_on_aws_s3(file_path):
        aws_out = subprocess.check_output(
            ["aws", "s3", "ls", file_path, "--no-sign-request", "--human-readable"],
            text=True,
        )
        if Path(file_path).name not in aws_out:
            msg = f"File path '{file_path}' not found on AWS S3 Open Data!"
            raise ValueError(msg)
    else:
        if not Path(file_path).exists():
            msg = f"File path '{file_path}' does not exist in local file system!"
            raise ValueError(msg)


def _check_required_contents(
    file_path: str, contents: list[str], *, is_directory: bool
) -> None:
    """Validate that required files exist within a path.

    Args:
        file_path: Path to check (local or AWS S3).
        contents: List of required file names.
        is_directory: Whether the path is a directory.
    """
    if len(contents) == 0:
        return

    if _is_on_aws_s3(file_path):
        sep = "/" if is_directory else ""
        aws_out = subprocess.check_output(
            ["aws", "s3", "ls", f"{file_path}{sep}", "--no-sign-request", "--human-readable"],
            text=True,
        )
        for file in contents:
            if file not in aws_out:
                msg = f"Required content '{file}' not found on AWS path '{file_path}'!"
                raise ValueError(msg)
    else:
        if is_directory:
            files_in_dir = {
                str(path.relative_to(file_path)): path
                for path in Path(file_path).rglob("*")
                if path.is_file()
            }
            for file in contents:
                if file not in files_in_dir:
                    msg = f"Required content '{file}' not found in '{file_path}'!"
                    raise ValueError(msg)
        else:
            for file in contents:
                if Path(file_path).name != file:
                    msg = f"Required content '{file}' does not match '{file_path}'!"
                    raise ValueError(msg)


def _check_matrix_folder(file_path: str) -> None:
    """Validate connectivity matrix folder contents.

    Checks that matrix_config.json exists and all referenced matrix files are present.
    """
    if _is_on_aws_s3(file_path):
        L.warning("Matrix folder check skipped for AWS directory")
        return

    matrix_files = {
        str(path.relative_to(file_path)): path
        for path in Path(file_path).rglob("*")
        if path.is_file()
    }
    L.info(f"{len(matrix_files)} files in '{file_path}'")

    if "matrix_config.json" not in matrix_files:
        msg = "matrix_config.json missing!"
        raise ValueError(msg)

    with Path(matrix_files["matrix_config.json"]).open(encoding="utf-8") as f:
        mat_cfg = json.load(f)

    for pop in mat_cfg:
        for mat in mat_cfg[pop].values():
            mpath = mat["path"]
            if mpath not in matrix_files:
                msg = f"Matrix file '{mpath}' referenced in config but not found!"
                raise ValueError(msg)


CIRCUIT_ASSET_MAPPING: dict[str, dict] = {
    "sonata_circuit": {
        "is_directory": True,
        "content_type": "application/vnd.directory",
        "required_contents": ["circuit_config.json", "node_sets.json"],
        "required_validations": [],
    },
    "compressed_sonata_circuit": {
        "is_directory": False,
        "content_type": "application/gzip",
        "required_contents": ["circuit.gz"],
        "required_validations": [],
    },
    "circuit_connectivity_matrices": {
        "is_directory": True,
        "content_type": "application/vnd.directory",
        "required_contents": ["matrix_config.json"],
        "required_validations": [_check_matrix_folder],
    },
    "circuit_visualization": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["circuit_visualization.webp"],
        "required_validations": [],
    },
    "node_stats": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["node_stats.webp"],
        "required_validations": [],
    },
    "network_stats_a": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["network_stats_a.webp"],
        "required_validations": [],
    },
    "network_stats_b": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["network_stats_b.webp"],
        "required_validations": [],
    },
    "simulation_designer_image": {
        "is_directory": False,
        "content_type": "image/png",
        "required_contents": ["simulation_designer_image.png"],
        "required_validations": [],
    },
}


def register_asset(
    client: Client,
    file_path: str | None,
    asset_label: str,
    registered_circuit: models.Circuit,
    *,
    check_only: bool,
) -> models.Asset | None:
    """Register an asset for a circuit entity.

    Supports both local file system and AWS S3 Open Data paths.
    Validates the asset label, file existence, and required contents before registration.

    Args:
        client: The entitycore SDK client.
        file_path: Path to the asset (local or S3). None to skip.
        asset_label: Label identifying the asset type (must be in CIRCUIT_ASSET_MAPPING).
        registered_circuit: The circuit entity to attach the asset to.
        check_only: If True, perform validation only without registering.

    Returns:
        The registered asset, or None if skipped or check_only.
    """
    if file_path is None:
        L.info(f"No path for '{asset_label}' asset provided - skipping")
        return None

    if asset_label not in CIRCUIT_ASSET_MAPPING:
        msg = f"Asset label '{asset_label}' not supported!"
        raise ValueError(msg)

    # Normalize trailing slash (Needed for aws s3 ls!!)
    if file_path.endswith("/"):
        file_path = file_path[:-1]

    _check_file_path(file_path)

    # Validate required contents
    asset_config = CIRCUIT_ASSET_MAPPING[asset_label]
    is_dir = asset_config["is_directory"]
    _check_required_contents(
        file_path,
        asset_config.get("required_contents", []),
        is_directory=is_dir,
    )

    # Run additional validations
    for val_fct in asset_config.get("required_validations", []):
        val_fct(file_path)

    content_type = asset_config["content_type"]

    if check_only:
        L.info(f"Asset '{asset_label}': CHECK ONLY (not registered)")
        return None

    # Register on AWS S3
    if _is_on_aws_s3(file_path):
        storage_path = Path(file_path).relative_to(AWS_S3_ROOT)
        asset_name = asset_label if is_dir else storage_path.name
        asset = client.register_asset(
            asset_label=asset_label,
            name=asset_name,
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            storage_path=str(storage_path),
            storage_type="aws_s3_open",
            is_directory=is_dir,
            content_type=content_type,
        )
        L.info(f"'{asset_label}' asset registered (AWS S3) under ID {asset.id}")
        return asset

    # Upload from local file system
    if is_dir:
        files_in_dir = {
            str(path.relative_to(file_path)): path
            for path in Path(file_path).rglob("*")
            if path.is_file()
        }
        # Filter out .DS_Store files
        num_ignored = sum(1 for f in files_in_dir if ".ds_store" in f.lower())
        if num_ignored > 0:
            L.warning(f"{num_ignored} '.DS_Store' file(s) found in '{file_path}' - ignoring")
        files_in_dir = {
            k: v for k, v in files_in_dir.items() if ".ds_store" not in k.lower()
        }
        asset = client.upload_directory(
            label=asset_label,
            name=asset_label,
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            paths=files_in_dir,
        )
    else:
        asset = client.upload_file(
            asset_label=asset_label,
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            file_path=file_path,
            file_content_type=content_type,
        )
    L.info(f"'{asset_label}' asset uploaded under ID {asset.id}")
    return asset


# --- Derivation, contributions, and publication links ---


def register_derivation(
    client: Client,
    from_entity: models.Circuit | None,
    derivation_type: str,
    registered_circuit: models.Circuit,
    *,
    check_only: bool,
) -> models.Derivation | None:
    """Register a derivation link between a parent and a derived circuit.

    Args:
        client: The entitycore SDK client.
        from_entity: The parent circuit entity (None to skip).
        derivation_type: The type of derivation (must be a valid DerivationType).
        registered_circuit: The derived circuit entity.
        check_only: If True, perform validation only without registering.

    Returns:
        The registered derivation, or None if skipped or check_only.
    """
    if from_entity is None:
        L.info("No derivation parent provided - skipping")
        return None

    valid_derivation_types = [str(_dtype) for _dtype in DerivationType]
    if derivation_type not in valid_derivation_types:
        msg = f"Derivation type '{derivation_type}' unknown (valid: {valid_derivation_types})!"
        raise ValueError(msg)

    if check_only:
        L.info(f"Derivation '{derivation_type}': CHECK ONLY (not registered)")
        return None

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
        entity_type=models.Contribution, query={"entity__id": contr_model.entity.id}
    ).all()
    for _r in res:
        if (
            _r.agent.pref_label == contr_model.agent.pref_label
            and _r.agent.type == contr_model.agent.type
            and _r.role.name == contr_model.role.name
        ):
            return _r
    return None


def register_contributions(
    client: Client,
    contribution_dict: dict,
    registered_circuit: models.Circuit,
    *,
    check_only: bool,
) -> list[models.Contribution]:
    """Register contributions for a circuit entity.

    Skips contributions that already exist (deduplication).

    Args:
        client: The entitycore SDK client.
        contribution_dict: Resolved contributions (from get_contributions).
        registered_circuit: The circuit entity.
        check_only: If True, perform validation only without registering.

    Returns:
        List of newly registered contribution entities.
    """
    if check_only:
        L.info(f"Contributions: {len(contribution_dict)} (CHECK ONLY)")
        return []

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
            L.warning(f"Contribution for agent '{cdict['agent'].pref_label}' already exists - skipping")
    L.info(f"Contributions: {len(contributions_list)} registered")
    return contributions_list


def register_publication_links(
    client: Client,
    publication_dict: dict,
    registered_circuit: models.Circuit,
    *,
    check_only: bool,
) -> list[models.ScientificArtifactPublicationLink]:
    """Register publication links for a circuit entity.

    Skips links that already exist (deduplication).

    Args:
        client: The entitycore SDK client.
        publication_dict: Resolved publications (from get_publications).
        registered_circuit: The circuit entity.
        check_only: If True, perform validation only without registering.

    Returns:
        List of newly registered publication link entities.
    """
    if check_only:
        L.info(f"Publication links: {len(publication_dict)} (CHECK ONLY)")
        return []

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


# --- Additional circuit asset registration ---


def generate_compressed_circuit_asset(
    client: Client, circuit_path: Path, circuit_entity: models.Circuit, output_dir: Path
) -> None:
    """Generate a compressed circuit archive and register it as an asset."""
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

    try:
        compressed_circuit = circuit_utils.run_circuit_folder_compression(
            circuit_path=circuit_path,
            circuit_name=circuit_entity.name,
            output_root=output_dir,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Circuit compression failed: {e}")
        return

    try:
        db_sdk.add_compressed_circuit_asset(
            client=client,
            compressed_file=compressed_circuit,
            registered_circuit=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Compressed circuit registration failed: {e}")


def generate_connectivity_matrix_asset(
    client: Client, circuit_path: Path, circuit_entity: models.Circuit, output_dir: Path
) -> tuple[Path | None, Path | None, str | None]:
    """Generate connectivity matrices and register them as an asset.

    Returns the matrix_dir, matrix_config, and edge_population for downstream use.
    """
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

    try:
        (
            matrix_dir,
            matrix_config,
            edge_population,
        ) = circuit_utils.run_connectivity_matrix_extraction(
            circuit_path=circuit_path,
            output_root=output_dir,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Connectivity matrix extraction failed: {e}")
        return None, None, None

    try:
        db_sdk.add_connectivity_matrix_asset(
            client=client,
            matrix_dir=matrix_dir,
            registered_circuit=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Connectivity matrix registration failed: {e}")

    return matrix_dir, matrix_config, edge_population


def generate_connectivity_plot_assets(
    client: Client,
    circuit_entity: models.Circuit,
    matrix_config: Path | None,
    edge_population: str | None,
    output_dir: Path,
) -> tuple[Path | None, list | None]:
    """Generate connectivity plots and register them as assets.

    Returns the plot_dir and plot_files for downstream use (overview figure generation).
    """
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

    if matrix_config is None or edge_population is None:
        return None, None

    try:
        plot_dir, plot_files = circuit_utils.run_basic_connectivity_plots(
            matrix_config=matrix_config,
            edge_population=edge_population,
            output_root=output_dir,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Connectivity plots generation failed: {e}")
        return None, None

    try:
        db_sdk.add_image_assets(
            client=client,
            plot_dir=plot_dir,
            plot_files=plot_files,
            registered_circuit=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Connectivity plots registration failed: {e}")

    return plot_dir, plot_files


def generate_overview_image_asset(
    client: Client,
    circuit_entity: models.Circuit,
    plot_dir: Path | None,
    output_dir: Path,
) -> None:
    """Generate the circuit overview image and register it as an asset."""
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

    try:
        viz_path = circuit_utils.generate_overview_figure(
            plot_dir, output_dir / "circuit_visualization.png"
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Overview image generation failed: {e}")
        return

    try:
        db_sdk.add_image_assets(
            client=client,
            plot_dir=output_dir,
            plot_files=[viz_path.name],
            registered_circuit=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Overview image registration failed: {e}")


def generate_sim_designer_image_asset(
    client: Client,
    circuit_entity: models.Circuit,
    plot_dir: Path | None,
    output_dir: Path,
) -> None:
    """Generate the simulation designer image and register it as an asset."""
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

    try:
        viz_path = circuit_utils.generate_overview_figure(
            plot_dir, output_dir / "simulation_designer_image.png"
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Simulation designer image generation failed: {e}")
        return

    try:
        db_sdk.add_image_assets(
            client=client,
            plot_dir=output_dir,
            plot_files=[viz_path.name],
            registered_circuit=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Simulation designer image registration failed: {e}")


def generate_additional_circuit_assets(
    db_client: Client,
    circuit_path: Path,
    circuit_entity: models.Circuit,
) -> None:
    """Generate and register additional circuit assets.

    Generates compressed circuit, connectivity matrices, connectivity plots,
    and overview figures. Each step is independent — failures are logged as
    warnings without aborting the remaining steps.

    Args:
        db_client: The entitycore SDK client.
        circuit_path: Path to the circuit_config.json file.
        circuit_entity: The registered circuit entity to attach assets to.
    """
    output_root = circuit_path.parents[1]
    circuit_name = circuit_path.parent.name

    generate_compressed_circuit_asset(
        client=db_client, circuit_path=circuit_path,
        circuit_entity=circuit_entity,
        output_dir=output_root / (circuit_name + "__COMPRESSED__"),
    )

    _, matrix_config, edge_population = generate_connectivity_matrix_asset(
        client=db_client, circuit_path=circuit_path,
        circuit_entity=circuit_entity,
        output_dir=output_root / (circuit_name + "__CONN_MATRIX__"),
    )

    plot_dir, _ = generate_connectivity_plot_assets(
        client=db_client,
        circuit_entity=circuit_entity, matrix_config=matrix_config,
        edge_population=edge_population,
        output_dir=output_root / (circuit_name + "__BASIC_PLOTS__"),
    )

    viz_dir = output_root / (circuit_name + "__CIRCUIT_VIZ__")

    generate_overview_image_asset(
        client=db_client,
        circuit_entity=circuit_entity, plot_dir=plot_dir,
        output_dir=viz_dir,
    )

    generate_sim_designer_image_asset(
        client=db_client,
        circuit_entity=circuit_entity, plot_dir=plot_dir,
        output_dir=viz_dir,
    )


# --- High-level registration functions ---


def register_circuit(
    client: Client,
    circuit_path: str | Path,
    *,
    name: str,
    description: str,
    build_category: types.CircuitBuildCategory,
    brain_region: models.BrainRegion,
    subject: models.Subject,
    contact_email: str | None = None,
    published_in: str | None = None,
    experiment_date: datetime | None = None,
    license: models.License | None = None,
    atlas: models.BrainAtlas | None = None,
    root: models.Circuit | UUID | None = None,
    parent: models.Circuit | UUID | None = None,
    derivation_type: DerivationType | None = None,
    contributions: dict | None = None,
    publications: dict | None = None,
    authorized_public: bool = False,
    check_only: bool = False,
) -> models.Circuit | None:
    """Register a circuit entity with all associated links and assets.

    This is the main entry point for tasks and programmatic registration.
    All entity references (subject, brain_region, license, parent) must already
    be resolved.

    Scale, neuron/synapse/connection counts, and circuit properties (morphologies,
    point neurons, electrical models, spines) are computed automatically from
    the circuit files. The SONATA circuit folder is registered as an asset.

    Args:
        client: The entitycore SDK client.
        circuit_path: Path to circuit_config.json (or the folder containing it).
        name: Circuit name.
        description: Circuit description.
        build_category: Build category (computational_model, em_reconstruction).
        brain_region: Resolved brain region entity.
        subject: Resolved subject entity.
        contact_email: Contact email address (optional).
        published_in: Human-readable publication string (optional).
        experiment_date: Experiment/build date (optional).
        license: Resolved license entity (optional).
        atlas: Brain atlas entity associated with the circuit (optional).
        root: Root circuit entity or root circuit ID (UUID) in the derivation
            hierarchy (optional).
        parent: Parent circuit entity or ID (UUID) for derivation linking (optional).
        derivation_type: Type of derivation (required if parent is provided).
        contributions: Resolved contributions dict (from get_contributions, optional).
        publications: Resolved publications dict (from get_publications, optional).
        authorized_public: Whether to make the circuit publicly accessible.
        check_only: If True, perform a dry run without registering anything.

    Returns:
        The registered circuit entity, or None if check_only is True.
    """
    # Resolve circuit_path to the circuit_config.json file
    circuit_path = Path(circuit_path)
    if circuit_path.is_dir():
        circuit_path = circuit_path / "circuit_config.json"
    if not circuit_path.exists():
        msg = f"Circuit config not found at '{circuit_path}'!"
        raise ValueError(msg)
    circuit_folder = circuit_path.parent

    # Compute scale, counts, and properties from circuit
    c = OBICircuit(name=name, path=str(circuit_path))
    scale, number_neurons, number_synapses, number_connections = get_circuit_size(c)
    has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
        get_circuit_properties(c)
    )
    L.info(
        f"Computed from circuit: scale={scale}, neurons={number_neurons}, "
        f"synapses={number_synapses}, connections={number_connections}"
    )

    # Build circuit model
    circuit_model = models.Circuit(
        name=name,
        description=description,
        subject=subject,
        brain_region=brain_region,
        license=license,
        number_neurons=number_neurons,
        number_synapses=number_synapses,
        number_connections=number_connections,
        has_morphologies=has_morphologies,
        has_point_neurons=has_point_neurons,
        has_electrical_cell_models=has_electrical_cell_models,
        has_spines=has_spines,
        scale=scale,
        build_category=build_category,
        root_circuit_id=root.id if isinstance(root, models.Circuit) else root,
        atlas_id=atlas.id if atlas is not None else None,
        contact_email=contact_email,
        published_in=published_in,
        experiment_date=experiment_date,
        authorized_public=authorized_public,
    )

    if check_only:
        L.info(f"Circuit entity '{circuit_model.name}': CHECK ONLY (not registered)")
        return None

    # 1. Register circuit entity
    registered_circuit = client.register_entity(circuit_model)
    L.info(f"Circuit '{registered_circuit.name}' registered under ID {registered_circuit.id}")

    # 2. Derivation link
    if parent is not None:
        if isinstance(parent, UUID):
            parent = client.get_entity(entity_id=parent, entity_type=models.Circuit)
        register_derivation(
            client=client,
            from_entity=parent,
            derivation_type=derivation_type,
            registered_circuit=registered_circuit,
            check_only=False,
        )

    # 3. Contributions
    if contributions:
        register_contributions(
            client=client,
            contribution_dict=contributions,
            registered_circuit=registered_circuit,
            check_only=False,
        )

    # 4. Publication links
    if publications:
        register_publication_links(
            client=client,
            publication_dict=publications,
            registered_circuit=registered_circuit,
            check_only=False,
        )

    # 5. Register SONATA circuit folder asset
    register_asset(
        client=client,
        file_path=str(circuit_folder),
        asset_label="sonata_circuit",
        registered_circuit=registered_circuit,
        check_only=False,
    )

    # 6. Generate and register additional circuit assets
    generate_additional_circuit_assets(
        db_client=client,
        circuit_path=circuit_path,
        circuit_entity=registered_circuit,
    )

    return registered_circuit


def register_circuit_from_metadata(
    client: Client,
    circuit_metadata: dict,
    circuit_path: str | Path,
    *,
    contributions: dict | None = None,
    publications: dict | None = None,
    authorized_public: bool = False,
    check_only: bool = False,
) -> models.Circuit | None:
    """Register a circuit from user-provided metadata (resolving all entities).

    This is the top-level user-facing function. It resolves all entity references
    from string names in the metadata dict, computes counts/scale from the circuit
    files, and delegates to register_circuit().

    Args:
        client: The entitycore SDK client.
        circuit_metadata: Dictionary with circuit properties. Required keys:
            name, description, build_category, species, subject, brain_region.
            Optional keys: root, parent, derivation_type, license, published_in,
            contact, experiment_date.
        circuit_path: Path to the SONATA circuit folder (containing circuit_config.json)
            or directly to the circuit_config.json file.
        contributions: Raw contributions dict (agent name -> {type, role}).
            Will be resolved via get_contributions(). Optional.
        publications: Raw publications dict (DOI -> {type}).
            Will be resolved via get_publications(). Optional.
        authorized_public: Whether to make the circuit publicly accessible.
        check_only: If True, perform validation and dry run without registering.

    Returns:
        The registered circuit entity, or None if check_only is True.
    """
    # Validate and resolve all dependencies
    check_if_circuit_exists(client, circuit_metadata)

    subject = get_subject(client, circuit_metadata)
    brain_region = get_brain_region(client, circuit_metadata)
    license_entity = get_license(client, circuit_metadata)
    root = get_root_circuit(client, circuit_metadata)
    parent = get_parent_circuit(client, circuit_metadata)
    exp_date = get_exp_date(circuit_metadata)

    # Resolve contributions and publications
    contribution_dict = None
    if contributions:
        contribution_dict = get_contributions(client, contributions)

    publication_dict = None
    if publications:
        publication_dict = get_publications(client, publications)

    # Delegate to register_circuit with resolved entities
    return register_circuit(
        client=client,
        circuit_path=circuit_path,
        name=circuit_metadata["name"],
        description=circuit_metadata["description"],
        build_category=circuit_metadata["build_category"],
        brain_region=brain_region,
        subject=subject,
        contact_email=circuit_metadata.get("contact"),
        published_in=circuit_metadata.get("published_in"),
        experiment_date=exp_date,
        license=license_entity,
        root=root,
        parent=parent,
        derivation_type=circuit_metadata.get("derivation_type"),
        contributions=contribution_dict,
        publications=publication_dict,
        authorized_public=authorized_public,
        check_only=check_only,
    )
