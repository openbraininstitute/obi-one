"""Utilities for registering circuit entities to entitycore."""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
from entitysdk import Client, models, types
from entitysdk.types import DerivationType

L = logging.getLogger(__name__)

AWS_S3_ROOT = "s3://openbluebrain"


def get_circuit(
    client: Client, circuit_name: str | None, must_exist: bool = False
) -> models.Circuit | None:
    if circuit_name is None:
        return None

    res = client.search_entity(
        entity_type=models.Circuit, query={"name": circuit_name}
    ).all()
    if len(res) == 0:
        if must_exist:
            msg = f"Circuit '{circuit_name}' not found!"
            raise ValueError(msg)
        else:
            return None
    else:
        for c in res:
            print(f"Circuit '{circuit_name}' found under ID {c.id}.")
        if len(res) == 1:
            return res[0]
        else:
            msg = "Multiple circuits found!"
            raise ValueError(msg)


def check_if_circuit_exists(client: Client, circuit_metadata: dict) -> bool:
    circuit_name = circuit_metadata.get("name")
    if circuit_name is None:
        msg = "Circuit name missing!"
        raise ValueError(msg)
    if get_circuit(client, circuit_name, must_exist=False) is not None:
        msg = "Circuit already exists!"
        raise ValueError(msg)
    print(f"Circuit '{circuit_name}' not yet registered.")


def get_root_circuit(client: Client, circuit_metadata: dict) -> models.Circuit | None:
    root_name = circuit_metadata.get("root")
    root = get_circuit(client, root_name, must_exist=True)
    if root is None:
        print(f"Root circuit: {root}")
    else:
        print(f"Root circuit: {root.name} (ID {root.id})")
    return root


def get_parent_circuit(client: Client, circuit_metadata: dict) -> models.Circuit | None:
    parent_name = circuit_metadata.get("parent")
    parent = get_circuit(client, parent_name, must_exist=True)
    if parent is None:
        print(f"Parent circuit: {parent}")
        if circuit_metadata["derivation_type"] is not None:
            msg = f"Derivation type '{circuit_metadata['derivation_type']}' requires a parent circuit!"
            raise ValueError(msg)
    else:
        print(f"Parent circuit: {parent.name} (ID {parent.id})")
        valid_derivation_types = [str(_dtype) for _dtype in DerivationType]
        if circuit_metadata["derivation_type"] not in valid_derivation_types:
            msg = f"A valid derivation type is required (valid: {valid_derivation_types})!"
            raise ValueError(msg)
    return parent


def check_counts(circuit_metadata: dict) -> None:
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
        msg = f"Number of neurons ({nnrn}) does not match circuit scale '{circuit_metadata['scale']}'!"
        raise ValueError(msg)
    print(f"#Neurons: {nnrn}, #Synapses: {nsyn}, #Connections: {nconn}, Scale: {scale}")


def get_exp_date(circuit_metadata: dict) -> datetime | None:
    exp_date_str = circuit_metadata.get("experiment_date")
    if exp_date_str is None:
        exp_date = None
    else:
        try:
            exp_date = datetime.strptime(exp_date_str, "%d.%m.%Y")
        except ValueError:
            exp_date = None

        if exp_date is None:
            try:
                exp_date = datetime.strptime(exp_date_str, "%B, %Y")
            except ValueError:
                exp_date = None

        if exp_date is None:
            msg = "Date format not supported!"
            raise ValueError(msg)
    print(f"Experiment date: {exp_date}")
    return exp_date


def find_agent(
    client: Client, agent_name: str, agent_type: str
) -> models.Consortium | models.Organization | models.Person:
    entity_type = getattr(models, agent_type.title())
    agents = client.search_entity(
        entity_type=entity_type, query={"pref_label": agent_name}
    ).all()
    if len(agents) == 0:
        msg = f"{agent_type.title()} '{agent_name}' not found!"
        raise ValueError(msg)
    else:
        if len(agents) > 1:
            print(
                f"WARNING: {agent_type.title()} '{agent_name}' found multiple times - using first instance!"
            )
        agent = agents[0]
    return agent


def find_role(client: Client, role) -> models.Role:
    all_roles = client.search_entity(entity_type=models.Role).all()
    role = [_role for _role in all_roles if _role.name == role]
    if len(role) != 1:
        msg = f"Role '{role}' not found or multiple entities exist!"
        raise ValueError(msg)
    role = role[0]
    return role


def get_contributions(
    client: Client, circuit_contributions: dict, verbose: bool = False
) -> dict:
    contr_entities = {}
    contr_counts = {}
    for cname, cdict in circuit_contributions.items():
        agent = find_agent(client, cname, cdict.get("type"))
        role = find_role(client, cdict.get("role"))
        contr_entities[cname] = {"agent": agent, "role": role}
        if verbose:
            print(
                f"Contributing {agent.type} '{agent.pref_label}' (ID {agent.id}) with role '{role.name}' (ID {role.id})"
            )
        if agent.type.title() in contr_counts:
            contr_counts[agent.type.title()] += 1
        else:
            contr_counts[agent.type.title()] = 1
    print(f"Contributors: {contr_counts}")
    return contr_entities


def get_publications(
    client: Client, circuit_publications: dict, verbose: bool = False
) -> dict:
    publ_entities = {}
    publ_counts = {}
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
            msg = f"Publication with DOI {doi} found multiple times - THIS SHOULD NOT BE POSSIBLE."
            raise ValueError(msg)
        publ = res[0]
        publ_entities[doi] = {"entity": publ, "type": publ_type}
        if verbose:
            print(f"Publication {doi} (ID {publ.id}) of type '{publ_type}'")
        if publ_type.title() in publ_counts:
            publ_counts[publ_type.title()] += 1
        else:
            publ_counts[publ_type.title()] = 1
    print(f"Publications: {publ_counts}")
    return publ_entities


def get_subject(client: Client, circuit_metadata: dict) -> models.Subject:
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
    print(f"Subject '{subject.name}' (ID {subject.id})")

    # Check consistency with species
    species_name = circuit_metadata.get("species")
    if subject.species.name != species_name:
        msg = f"Subject '{subject.name}' and species '{species_name}' are inconsistent!"
        raise ValueError(msg)

    return subject


def get_brain_region(client: Client, circuit_metadata: dict) -> models.BrainRegion:
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
    print(f"Brain region '{brain_region.name}' (ID {brain_region.id})")
    return brain_region


def get_license(client: Client, circuit_metadata: dict) -> models.License | None:
    lic_name = circuit_metadata.get("license")
    if lic_name is None:
        print("WARNING: No license specified!")
        return None

    license = client.search_entity(
        entity_type=models.License, query={"label": lic_name}
    ).all()
    if len(license) == 0:
        msg = f"License '{lic_name}' not found! Licenses need to be registered beforehand."
        raise ValueError(msg)
    if len(license) > 1:
        msg = f"Multiple licenses with name '{lic_name}' found!"
        raise ValueError(msg)
    license = license[0]
    print(f"License '{license.label}' {license.name} (ID {license.id})")
    return license


def register_circuit_entity(
    client: Client,
    circuit_metadata: dict,
    subject: models.Subject,
    brain_region: models.BrainRegion,
    license: models.License | None,
    root: models.Circuit | None,
    exp_date: datetime,
    *,
    make_public: bool,
    check_only: bool,
) -> models.Circuit:
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
        authorized_public=make_public,  # Make it public
    )

    # Register new circuit entity
    if check_only:
        print(f"Circuit entity '{circuit_model.name}': ***CHECK ONLY***")
        registered_circuit = None
    else:
        registered_circuit = client.register_entity(circuit_model)
        print(f"Circuit entity '{registered_circuit.name}': ID {registered_circuit.id}")
    return registered_circuit


def check_matrix_folder(file_path: str) -> None:
    if is_on_AWS_S3(file_path):
        print("WARNING: Matrix folder check skipped for AWS directory.")
        return

    matrix_files = {
        str(path.relative_to(file_path)): path
        for path in Path(file_path).rglob("*")
        if path.is_file()
    }
    print(f"{len(matrix_files)} files in '{file_path}':")
    print("\n".join(matrix_files.keys()))

    # Check consistency
    if "matrix_config.json" not in matrix_files:
        msg = "ERROR: matrix_config.json missing!"
        raise ValueError(msg)

    with open(matrix_files["matrix_config.json"], "r") as f:
        mat_cfg = json.load(f)

    for pop in mat_cfg:
        for mat in mat_cfg[pop].values():
            mpath = mat["path"]
            if mpath not in matrix_files:
                msg = f"ERROR: Matrix '{mpath}' not found!"
                raise ValueError(msg)


def is_on_AWS_S3(file_path: str) -> bool:
    if file_path.lower().startswith(AWS_S3_ROOT):
        return True
    else:
        return False


def check_file_path(file_path: str) -> None:
    if len(file_path) == 0:
        msg = "File path missing!"
        raise ValueError(msg)

    if is_on_AWS_S3(file_path):
        aws_out = subprocess.check_output(
            f"aws s3 ls {file_path} --no-sign-request --human-readable",
            shell=True,
            text=True,
        )
        if Path(file_path).name not in aws_out:
            msg = f"File path '{file_path}' not found on AWS S3 Open Data!"
            raise ValueError(msg)
    else:
        if not Path(file_path).exists():
            msg = f"File path '{file_path}' does not exist in local file system!"
            raise ValueError(msg)


def check_required_contents(
    file_path: str, contents: list, *, is_directory: bool
) -> None:
    if len(contents) == 0:
        # Nothing to check
        return

    if is_on_AWS_S3(file_path):
        if is_directory:
            sep = "/"  # aws s3 ls <path-to-folder>/ will list folder contents
        else:
            sep = ""  # aws s3 ls <path-to-file> will list actual file
        aws_out = subprocess.check_output(
            f"aws s3 ls {file_path}{sep} --no-sign-request --human-readable",
            shell=True,
            text=True,
        )
        for file in contents:
            if file not in aws_out:
                msg = f"File content '{file}' not found on AWS path '{file_path}'!"
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
                    msg = f"File content '{file}' not found in '{file_path}'!"
                    raise ValueError(msg)
        else:
            for file in contents:
                if Path(file_path).name != file:
                    msg = f"File content '{file}' does not match '{file_path}'!"
                    raise ValueError(msg)


CIRCUIT_ASSET_MAPPING = {
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
        "required_validations": [check_matrix_folder],
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
) -> models.Asset:
    asset = None
    if file_path is None:
        print(f"INFO: No path for '{asset_label}' asset provided - SKIPPING")
        return asset

    # Check asset label
    if asset_label not in CIRCUIT_ASSET_MAPPING:
        msg = f"Asset label '{asset_label}' not supported!"
        raise ValueError(msg)

    # Check file path
    if file_path[-1] == "/":
        file_path = file_path[:-1]  # Needed for aws s3 ls!!
    check_file_path(file_path)

    # Check required contents
    is_dir = CIRCUIT_ASSET_MAPPING[asset_label]["is_directory"]
    check_required_contents(
        file_path,
        CIRCUIT_ASSET_MAPPING[asset_label].get("required_contents", []),
        is_directory=is_dir,
    )

    # Run required validations
    for val_fct in CIRCUIT_ASSET_MAPPING[asset_label].get("required_validations", []):
        val_fct(file_path)

    # Register asset
    content_type = CIRCUIT_ASSET_MAPPING[asset_label]["content_type"]
    if is_on_AWS_S3(file_path):
        storage_path = Path(file_path).relative_to(AWS_S3_ROOT)
        asset_name = asset_label if is_dir else storage_path.name
        storage_type = "aws_s3_open"
        if check_only:
            print(f"assetID ({asset_label} on AWS): ***CHECK ONLY***")
            print(
                f"[name={asset_name}, storage_path={storage_path}, storage_type={storage_type}, is_directory={is_dir}, content_type={content_type}]"
            )
        else:
            asset = client.register_asset(
                asset_label=asset_label,
                name=asset_name,
                entity_id=registered_circuit.id,
                entity_type=models.Circuit,
                storage_path=str(storage_path),
                storage_type=storage_type,
                is_directory=is_dir,
                content_type=content_type,
            )
            print(f"assetID ({asset_label} on AWS): {asset.id}")
    else:  # Upload from local file system
        files_in_dir = []
        if is_dir:
            files_in_dir = {
                str(path.relative_to(file_path)): path
                for path in Path(file_path).rglob("*")
                if path.is_file()
            }
            num_ignore = np.sum(
                [".ds_store" in _file.lower() for _file in files_in_dir]
            )
            if num_ignore > 0:
                print(
                    f"WARNING: {num_ignore} '.DS_Store' file(s) found in `{file_path}` - IGNORING"
                )
            files_in_dir = {
                _k: _v
                for _k, _v in files_in_dir.items()
                if ".ds_store" not in _k.lower()
            }
        if check_only:
            print(f"assetID ({asset_label}): ***CHECK ONLY***")
            if is_dir:
                print(
                    f"[name={asset_label}, paths=<{len(files_in_dir)} in '{file_path}'>]"
                )
            else:
                print(f"[file_path={file_path}, file_content_type={content_type}]")
        else:
            if is_dir:
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
            print(f"assetID ({asset_label}): {asset.id}")
    return asset


def register_derivation(
    client: Client,
    from_entity: models.Circuit,
    derivation_type: DerivationType,
    registered_circuit: models.Circuit,
    *,
    check_only: bool,
) -> models.Derivation | None:
    registered_derivation = None
    if from_entity is None:
        print("INFO: No derivation parent provided - SKIPPING")
        return registered_derivation

    if derivation_type not in [str(_dtype) for _dtype in DerivationType]:
        msg = f"ERROR: Derivation type '{derivation_type}' unknown!"
        raise ValueError(msg)

    if check_only:
        print(f"derivationID ({derivation_type}): ***CHECK ONLY***")
    else:
        derivation_model = models.Derivation(
            used=from_entity,
            generated=registered_circuit,
            derivation_type=derivation_type,
        )
        registered_derivation = client.register_entity(derivation_model)
        print(
            f"derivationID ({derivation_type}): REGISTERED w/o ID"
        )  # Note: registered_derivation.id is None
    return registered_derivation


def return_contribution_if_exists(
    client: Client, contr_model: models.Contribution
) -> models.Contribution | None:
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
) -> list:
    contributions_list = []
    if check_only:
        print(f"Contributions: {len(contribution_dict)} ***CHECK ONLY***")
    else:
        for cdict in contribution_dict.values():
            # Build model
            contr_model = models.Contribution(
                agent=cdict["agent"], role=cdict["role"], entity=registered_circuit
            )

            # Check if existing & register new entity
            registered_contr = return_contribution_if_exists(client, contr_model)
            if registered_contr is None:
                registered_contr = client.register_entity(contr_model)
                contributions_list.append(registered_contr)
            else:
                print(f"WARNING: Contribution '{cdict}' already exists - SKIPPING")
        print(f"Contributions: {len(contributions_list)} registered")
    return contributions_list


def register_publication_links(
    client: Client,
    publication_dict: dict,
    registered_circuit: models.Circuit,
    *,
    check_only: bool,
) -> list:
    publications_list = []
    if check_only:
        print(f"Publication links: {len(publication_dict)} ***CHECK ONLY***")
    else:
        for pdict in publication_dict.values():
            # Create model
            publ_link_model = models.ScientificArtifactPublicationLink(
                publication=pdict["entity"],
                scientific_artifact=registered_circuit,
                publication_type=pdict["type"],
            )

            # Check & register new entity
            res = client.search_entity(
                entity_type=models.ScientificArtifactPublicationLink,
                query={
                    "publication__DOI": publ_link_model.publication.DOI,
                    "scientific_artifact__id": publ_link_model.scientific_artifact.id,
                    "publication_type": publ_link_model.publication_type,
                },
            ).all()
            if len(res) == 0:
                registered_publ_link = client.register_entity(publ_link_model)
                publications_list.append(registered_publ_link)
            else:
                print(
                    f"WARNING: Publication link {pdict} already registered - SKIPPING"
                )
        print(f"Publication links: {len(publications_list)} registered")
    return publications_list
