"""High-level circuit registration functions."""

import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from entitysdk import Client, models, types
from entitysdk.types import DerivationType

from obi_one.db_sdk.registration.circuit.assets import register_asset
from obi_one.db_sdk.registration.circuit.generate import generate_additional_circuit_assets
from obi_one.db_sdk.registration.circuit.links import (
    register_contributions,
    register_derivation,
    register_publication_links,
)
from obi_one.db_sdk.registration.circuit.resolve import (
    check_hierarchy_species,
    check_if_circuit_exists,
    get_brain_region,
    get_brain_region_hierarchy,
    get_contributions,
    get_exp_date,
    get_license,
    get_parent_circuit,
    get_publications,
    get_root_circuit,
    get_subject,
)
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.scientific.tasks.circuit_validation.task import run_circuit_validation
from obi_one.utils.circuit import get_circuit_properties, get_circuit_size, run_validation
from obi_one.utils.io import extract_tar_gz

L = logging.getLogger(__name__)


def _resolve_target_simulator(
    target_simulator: types.TargetSimulator,
    circuit: OBICircuit,
) -> types.TargetSimulator:
    """Resolve target simulator from user input and circuit config.

    Checks consistency between the provided target_simulator and the value
    specified in the circuit config (if any).
    """
    cfg_target_simulator = circuit.sonata_circuit.config.get("target_simulator")
    if cfg_target_simulator and target_simulator != cfg_target_simulator:
        msg = (
            f"Specified target simulator '{target_simulator}' does not match"
            f" '{cfg_target_simulator}' in circuit config!"
        )
        raise ValueError(msg)
    return target_simulator


def _resolve_circuit_path(circuit_path: str | Path) -> tuple[Path, Path | None]:
    """Resolve circuit_path to the circuit_config.json file.

    If ``circuit_path`` is a .gz archive, it is extracted first and the original
    compressed path is returned as the second element.  Otherwise the second
    element is None.

    Returns:
        Tuple of (resolved circuit_config.json path, compressed path or None).
    """
    circuit_path = Path(circuit_path)
    circuit_path_compressed: Path | None = None

    if circuit_path.suffix == ".gz":
        circuit_path_compressed = circuit_path
        circuit_path = extract_tar_gz(circuit_path, clean=True)
        L.info(f"Extracted compressed circuit '{circuit_path_compressed}' to '{circuit_path}'")

    if circuit_path.is_dir():
        config_candidate = circuit_path / "circuit_config.json"
        if not config_candidate.exists():
            # Archive may contain a single top-level directory; look one level deeper
            subdirs = [d for d in circuit_path.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                config_candidate = subdirs[0] / "circuit_config.json"
        circuit_path = config_candidate
    if not circuit_path.exists():
        msg = f"Circuit config not found at '{circuit_path}'!"
        raise ValueError(msg)

    return circuit_path, circuit_path_compressed


def register_circuit(  # ruff: ignore[too-many-arguments, too-many-locals, complex-structure, too-many-branches, too-many-statements]
    client: Client,
    circuit_path: str | Path,
    *,
    name: str,
    description: str,
    build_category: types.CircuitBuildCategory,
    brain_region: models.BrainRegion,
    subject: models.Subject,
    target_simulator: types.TargetSimulator,
    scale_override: types.CircuitScale | None = None,
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
    skip_additional_assets: bool = False,
    skip_validation: bool = False,
    include_visualization: bool = True,
    lifecycle_status: types.EntityLifecycleStatus | str | None = None,
    overview_image_path: str | Path | None = None,
    sim_designer_image_path: str | Path | None = None,
    dry_run: bool = False,
    neurodamus_validation: bool = False,
) -> models.Circuit | None:
    """Register a circuit entity with all associated links and assets.

    This is the main entry point for tasks and programmatic registration.
    All entity references (subject, brain_region, license, parent) must already
    be resolved.

    Scale, neuron/synapse/connection counts, and circuit properties (morphologies,
    point neurons, electrical models, spines) are computed automatically from
    the circuit files. The SONATA circuit folder is registered as an asset.

    For the HTTP draft → async-validate → assets flow, call with
    ``lifecycle_status="draft"`` and ``skip_validation=True``, then trigger
    the validation launch job. Sync registration (tasks/notebooks) leaves
    those defaults so validation and assets run in-process.

    Set ``neurodamus_validation=True`` to run the fuller MOD compile / HOC /
    snap validation in-process after registration (same checks as the
    neurodamus launch job, without the launch-system). The circuit is
    registered as ``draft`` first and transitions to ``active`` or
    ``disqualified`` based on the result.

    Args:
        client: The entitycore SDK client.
        circuit_path: Path to circuit_config.json (or the folder containing it,
            or a compressed .gz archive of the circuit folder).
        name: Circuit name.
        description: Circuit description.
        build_category: Build category (computational_model, em_reconstruction).
        brain_region: Resolved brain region entity.
        subject: Resolved subject entity.
        target_simulator: Target simulator for the circuit.
        scale_override: If provided, override the automatically computed circuit scale.
            Only works for scales greater than 'small' (e.g. microcircuit, whole-brain).
        contact_email: Contact email address (optional).
        published_in: Human-readable publication string (optional).
        experiment_date: Experiment/build date (optional).
        license: Resolved license entity (optional).
        atlas: Brain atlas entity associated with the circuit (optional).
        root: Root circuit entity or root circuit ID (UUID) in the derivation
            hierarchy (optional). When omitted and ``parent`` is set, defaults to
            ``parent.root_circuit_id or parent.id``.
        parent: Parent circuit entity or ID (UUID) for derivation linking (optional).
        derivation_type: Type of derivation (required if parent is provided).
        contributions: Resolved contributions dict (from get_contributions, optional).
        publications: Resolved publications dict (from get_publications, optional).
        authorized_public: Whether to make the circuit publicly accessible.
        skip_additional_assets: If True, skip generation/registration of additional assets
            (compressed circuit, matrices, plots, figures).
        skip_validation: If True, skip SONATA circuit validation (e.g. when validation
            runs asynchronously after registration).
        include_visualization: When generating additional assets, also produce plots
            and overview / sim-designer images. Set False for post-validation jobs that
            only need compressed + connectivity matrices.
        lifecycle_status: Optional lifecycle status (e.g. ``"draft"`` for async
            validation). When omitted, entitycore's default applies.
        overview_image_path: Path to a pre-existing overview image file (.png or .webp).
            If provided, generation is skipped and this file is registered directly (optional).
        sim_designer_image_path: Path to a pre-existing simulation designer image file (.png).
            If provided, generation is skipped and this file is registered directly (optional).
        dry_run: If True, perform a dry run without registering anything.
        neurodamus_validation: If True, register as ``draft``, skip the light
            bluepysnap SONATA check, then run MOD compile / HOC / snap validation
            in-process and set lifecycle to ``active`` or ``disqualified``.

    Returns:
        The registered circuit entity, or None if dry_run is True.
    """
    if neurodamus_validation:
        skip_validation = True
        lifecycle_status = "draft"

    # Validate that a license is provided for public circuits
    if authorized_public and license is None:
        msg = "A license is required when registering a public circuit (authorized_public=True)."
        raise ValueError(msg)
    # Validate species consistency
    if (
        brain_region.species is not None
        and subject.species is not None
        and brain_region.species.id != subject.species.id
    ):
        msg = (
            f"Species mismatch: brain region '{brain_region.name}'"
            f" ('{brain_region.species.name}') does not match"
            f" subject species '{subject.species.name}'!"
        )
        raise ValueError(msg)

    # Resolve circuit_path to the circuit_config.json file
    circuit_path, circuit_path_compressed = _resolve_circuit_path(circuit_path)
    circuit_folder = circuit_path.parent

    # Validate provided image paths
    overview_image_path = Path(overview_image_path) if overview_image_path else None
    sim_designer_image_path = Path(sim_designer_image_path) if sim_designer_image_path else None
    if overview_image_path is not None and not overview_image_path.exists():
        msg = f"Overview image file not found: '{overview_image_path}'"
        raise FileNotFoundError(msg)
    if sim_designer_image_path is not None and not sim_designer_image_path.exists():
        msg = f"Sim designer image file not found: '{sim_designer_image_path}'"
        raise FileNotFoundError(msg)

    # Validate SONATA circuit
    if not skip_validation:
        run_validation(circuit_path)

    # Assure target simulator consistency
    c = OBICircuit(name=name, path=str(circuit_path))
    target_simulator = _resolve_target_simulator(target_simulator, c)

    # Compute scale, counts, and properties from circuit
    scale, number_neurons, number_synapses, number_connections = get_circuit_size(
        c, scale_override=scale_override
    )
    has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
        get_circuit_properties(c)
    )
    L.info(
        f"Circuit size & properties: scale={scale}, neurons={number_neurons}, "
        f"synapses={number_synapses}, connections={number_connections}, "
        f"has_morphologies={has_morphologies}, has_point_neurons={has_point_neurons}, "
        f"has_electrical_cell_models={has_electrical_cell_models}, has_spines={has_spines}"
    )

    # Resolve parent and derive root when not explicitly provided
    if parent is not None and isinstance(parent, UUID):
        parent = client.get_entity(entity_id=parent, entity_type=models.Circuit)
    if root is None and parent is not None:
        root = parent.root_circuit_id or parent.id

    # Build circuit model
    circuit_kwargs: dict = {
        "name": name,
        "description": description,
        "subject": subject,
        "brain_region": brain_region,
        "license": license,
        "number_neurons": number_neurons,
        "number_synapses": number_synapses,
        "number_connections": number_connections,
        "has_morphologies": has_morphologies,
        "has_point_neurons": has_point_neurons,
        "has_electrical_cell_models": has_electrical_cell_models,
        "has_spines": has_spines,
        "scale": scale,
        "build_category": build_category,
        "target_simulator": target_simulator,
        "root_circuit_id": root.id if isinstance(root, models.Circuit) else root,
        "atlas_id": atlas.id if atlas is not None else None,
        "contact_email": contact_email,
        "published_in": published_in,
        "experiment_date": experiment_date,
        "authorized_public": authorized_public,
    }
    if lifecycle_status is not None:
        circuit_kwargs["lifecycle_status"] = lifecycle_status
    circuit_model = models.Circuit(**circuit_kwargs)

    # Register circuit entity
    if dry_run:
        L.info(f"Circuit entity '{circuit_model.name}': DRY RUN (not registered)")
        registered_circuit = None
    else:
        registered_circuit = client.register_entity(circuit_model)
        L.info(f"Circuit '{registered_circuit.name}' registered under ID {registered_circuit.id}")

    # Derivation link
    if parent is not None:
        register_derivation(
            client=client,
            from_entity=parent,
            derivation_type=derivation_type,
            registered_circuit=registered_circuit,
            dry_run=dry_run,
        )

    # Contributions
    if contributions:
        register_contributions(
            client=client,
            contribution_dict=contributions,
            registered_circuit=registered_circuit,
            dry_run=dry_run,
        )

    # Publication links
    if publications:
        register_publication_links(
            client=client,
            publication_dict=publications,
            registered_circuit=registered_circuit,
            dry_run=dry_run,
        )

    # Register SONATA circuit folder asset
    register_asset(
        client=client,
        file_path=circuit_folder,
        asset_label="sonata_circuit",
        registered_circuit=registered_circuit,
        dry_run=dry_run,
    )

    # Generate and register additional circuit assets
    if not skip_additional_assets:
        edge_pop = c.default_edge_population_name if scale != types.CircuitScale.single else None
        generate_additional_circuit_assets(
            circuit_path=circuit_path,
            edge_population=edge_pop,
            circuit_path_compressed=circuit_path_compressed,
            overview_image_path=overview_image_path,
            sim_designer_image_path=sim_designer_image_path,
            client=client,
            circuit_entity=registered_circuit,
            include_visualization=include_visualization,
        )

    if neurodamus_validation and not dry_run and registered_circuit is not None:
        result = run_circuit_validation(
            db_client=client,
            circuit_id=registered_circuit.id,
        )
        if not result["valid"]:
            errors = "; ".join(result["errors"]) or "unknown validation error"
            msg = f"Neurodamus validation failed for circuit '{name}': {errors}"
            raise ValueError(msg)
        registered_circuit = client.get_entity(
            entity_id=registered_circuit.id, entity_type=models.Circuit
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
    include_visualization: bool = True,
    overview_image_path: str | Path | None = None,
    sim_designer_image_path: str | Path | None = None,
    dry_run: bool = False,
    neurodamus_validation: bool = False,
) -> models.Circuit | None:
    """Register a circuit from user-provided metadata (resolving all entities).

    This is the top-level user-facing function. It resolves all entity references
    from string names in the metadata dict, computes counts/scale from the circuit
    files, and delegates to register_circuit().

    Args:
        client: The entitycore SDK client.
        circuit_metadata: Dictionary with circuit properties. Required keys:
            name, description, build_category, species, subject, brain_region,
            brain_region_hierarchy, target_simulator.
            Optional keys: root, parent, derivation_type, license, published_in,
            contact, experiment_date.
        circuit_path: Path to the SONATA circuit folder (containing circuit_config.json),
            directly to the circuit_config.json file, or a compressed .gz archive.
        contributions: Raw contributions dict (agent name -> {type, role}).
            Will be resolved via get_contributions(). Optional.
        publications: Raw publications dict (DOI -> {type}).
            Will be resolved via get_publications(). Optional.
        authorized_public: Whether to make the circuit publicly accessible.
        include_visualization: When generating additional assets, also produce plots
            and overview / sim-designer images. Defaults to True.
        overview_image_path: Path to a pre-existing overview image file (.png or .webp).
            If provided, generation is skipped and this file is registered directly (optional).
        sim_designer_image_path: Path to a pre-existing simulation designer image file (.png).
            If provided, generation is skipped and this file is registered directly (optional).
        dry_run: If True, perform validation and dry run without registering.
        neurodamus_validation: If True, run MOD compile / HOC / snap validation
            in-process after registration (no launch-system job).

    Returns:
        The registered circuit entity, or None if dry_run is True.
    """
    # Validate and resolve all dependencies
    check_if_circuit_exists(client, circuit_metadata)

    subject = get_subject(client, circuit_metadata)
    brain_hierarchy = get_brain_region_hierarchy(client, circuit_metadata)
    check_hierarchy_species(brain_hierarchy, subject)
    brain_region = get_brain_region(client, circuit_metadata, brain_hierarchy)
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
        target_simulator=circuit_metadata["target_simulator"],
        scale_override=circuit_metadata.get("scale_override"),
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
        include_visualization=include_visualization,
        overview_image_path=overview_image_path,
        sim_designer_image_path=sim_designer_image_path,
        dry_run=dry_run,
        neurodamus_validation=neurodamus_validation,
    )
