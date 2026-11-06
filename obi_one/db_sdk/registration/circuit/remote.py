"""Circuit registration with validation and asset generation delegated to the obi-one service."""

import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx
from entitysdk import Client, models, types
from entitysdk.types import DerivationType

from obi_one.db_sdk.registration.circuit.register import register_circuit

L = logging.getLogger(__name__)


def register_circuit_with_remote_validation(  # ruff: ignore[too-many-arguments]
    client: Client,
    circuit_path: str | Path,
    *,
    obi_one_client: httpx.Client,
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
    derived_from_emodel: models.EModel | list[models.EModel] | None = None,
    derivation_type: DerivationType | None = None,
    derivation_label: str | list[str] | None = None,
    contributions: dict | None = None,
    publications: dict | None = None,
    authorized_public: bool = False,
    overview_image_path: str | Path | None = None,
    sim_designer_image_path: str | Path | None = None,
    dry_run: bool = False,
) -> tuple[models.Circuit, UUID | None]:
    """Register a circuit as draft and let the obi-one service validate it.

    Alternative to ``POST /declared/circuit/register`` for circuits that exceed the 2 GB
    per-file upload limit of the infrastructure layer. The circuit files are uploaded
    straight to entitycore through the SDK, so the limit does not apply.

    The flow matches the endpoint:

    1. ``register_circuit`` creates the circuit as ``draft`` and uploads the SONATA folder
       asset. Validation and generated assets (compressed circuit, connectivity matrices,
       plots, images) are deferred.
    2. ``POST /declared/circuit/{id}/validate?generate_assets=true`` starts the async
       validation job, which moves the circuit to ``active`` or ``disqualified`` and
       triggers asset generation on success.

    Both an uncompressed circuit folder and a compressed ``.gz`` archive are accepted
    (see ``register_circuit``).

    If the validation request fails, the draft circuit remains registered. Retry with
    ``POST /declared/circuit/{id}/validate?generate_assets=true``.

    Args:
        client: The entitycore SDK client. Its project context is forwarded to the service.
        circuit_path: Path to circuit_config.json, the folder containing it, or a
            compressed .gz archive of the circuit folder.
        obi_one_client: HTTP client for the obi-one service. It must have ``base_url`` set
            to the service URL (including any ``/api/obi-one`` prefix) and carry the
            ``Authorization`` header.
        name: Circuit name.
        description: Circuit description.
        build_category: Build category (computational_model, em_reconstruction).
        brain_region: Resolved brain region entity.
        subject: Resolved subject entity.
        target_simulator: Target simulator for the circuit.
        scale_override: Override the automatically computed circuit scale.
        contact_email: Contact email address (optional).
        published_in: Human-readable publication string (optional).
        experiment_date: Experiment/build date (optional).
        license: Resolved license entity (optional).
        atlas: Brain atlas entity associated with the circuit (optional).
        root: Root circuit entity or ID in the derivation hierarchy (optional).
        parent: Parent circuit entity or ID (optional).
        derived_from_emodel: EModel source(s) for ``emodel_circuit`` derivations (optional).
        derivation_type: Type of derivation for a parent circuit (optional).
        derivation_label: Label(s) for EModel derivations (optional).
        contributions: Resolved contributions dict (from get_contributions, optional).
        publications: Resolved publications dict (from get_publications, optional).
        authorized_public: Whether to make the circuit publicly accessible.
        overview_image_path: Pre-existing overview image (.png or .webp), registered
            immediately and not regenerated (optional).
        sim_designer_image_path: Pre-existing simulation designer image (.png), registered
            immediately and not regenerated (optional).
        dry_run: If True, validate the inputs and compute the circuit metadata without
            registering anything or contacting the obi-one service.

    Returns:
        Tuple of the draft circuit entity and the launch-system job ID of the validation
        job. The job can be followed with ``GET /declared/task/{job_id}``. With ``dry_run``
        the entity is the unregistered ``Circuit`` model and the job ID is ``None``.

    Raises:
        RuntimeError: If the validation request was rejected by the service.
    """
    registered = register_circuit(
        client=client,
        circuit_path=circuit_path,
        name=name,
        description=description,
        build_category=build_category,
        brain_region=brain_region,
        subject=subject,
        target_simulator=target_simulator,
        scale_override=scale_override,
        contact_email=contact_email,
        published_in=published_in,
        experiment_date=experiment_date,
        license=license,
        atlas=atlas,
        root=root,
        parent=parent,
        derived_from_emodel=derived_from_emodel,
        derivation_type=derivation_type,
        derivation_label=derivation_label,
        contributions=contributions,
        publications=publications,
        authorized_public=authorized_public,
        skip_validation=True,
        skip_additional_assets=True,
        lifecycle_status="draft",
        overview_image_path=overview_image_path,
        sim_designer_image_path=sim_designer_image_path,
        dry_run=dry_run,
    )
    if registered is None:
        msg = "Circuit registration returned no entity"
        raise RuntimeError(msg)
    if dry_run:
        return registered, None

    headers = {}
    if client.project_context is not None:
        headers = {
            "virtual-lab-id": str(client.project_context.virtual_lab_id),
            "project-id": str(client.project_context.project_id),
        }
    try:
        response = obi_one_client.post(
            f"/declared/circuit/{registered.id}/validate",
            params={"generate_assets": "true"},
            headers=headers,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        msg = (
            f"Circuit {registered.id} was registered as draft, but starting its validation"
            f" failed: {e}. Retry with POST /declared/circuit/{registered.id}/validate"
            "?generate_assets=true"
        )
        raise RuntimeError(msg) from e

    job_id = UUID(response.json()["job_id"])
    L.info("Validation job %s started for circuit %s", job_id, registered.id)
    return registered, job_id
