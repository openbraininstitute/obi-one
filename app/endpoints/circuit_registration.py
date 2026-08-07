"""Circuit registration endpoint."""

import json
import logging
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import entitysdk.client
from entitysdk import models
from entitysdk.models.core import Identifiable
from entitysdk.types import CircuitScale, DerivationType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.circuit_helpers import trigger_asset_generation_task, trigger_validation_task
from obi_one.db_sdk.registration.circuit import (
    check_hierarchy_species,
    check_if_circuit_exists,
    get_contributions,
    get_exp_date,
    get_publications,
    is_validation_allowed,
    register_circuit,
    validation_blocked_detail,
)

L = logging.getLogger(__name__)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _parse_json_object_form(value: str | None, field_name: str) -> dict[str, Any] | None:
    """Parse an optional JSON object from a multipart form field."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON for {field_name}: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a JSON object")
    return parsed


def _parse_experiment_date(value: str | None) -> datetime | None:
    """Parse experiment_date from ISO or metadata-supported formats."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        return get_exp_date({"experiment_date": value})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _parse_optional_enum[T](value: str | None, enum_cls: type[T], field_name: str) -> T | None:
    """Parse an optional string form field into an enum member."""
    if value is None:
        return None
    try:
        return enum_cls(value)  # type: ignore[call-arg]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid {field_name} '{value}'") from e


def _save_optional_upload(upload: UploadFile | None, dest_dir: Path) -> Path | None:
    """Persist an optional uploaded file into dest_dir; return its path or None."""
    if upload is None or not upload.filename:
        return None
    path = dest_dir / Path(upload.filename).name
    path.write_bytes(upload.file.read())
    return path


def _get_optional_entity[T: Identifiable](
    db_client: entitysdk.client.Client,
    entity_id: UUID | None,
    entity_type: type[T],
) -> T | None:
    """Fetch an entity by ID when provided, else return None."""
    if entity_id is None:
        return None
    return db_client.get_entity(entity_id=entity_id, entity_type=entity_type)


def _load_region_and_subject(
    db_client: entitysdk.client.Client,
    *,
    brain_region_id: UUID,
    subject_id: UUID,
) -> tuple[models.BrainRegion, models.Subject]:
    """Load brain region and subject, enforcing hierarchy/species consistency."""
    brain_region = db_client.get_entity(entity_id=brain_region_id, entity_type=models.BrainRegion)
    subject = db_client.get_entity(entity_id=subject_id, entity_type=models.Subject)
    hierarchy_id = getattr(brain_region, "hierarchy_id", None)
    if hierarchy_id is not None:
        hierarchy = db_client.get_entity(
            entity_id=hierarchy_id, entity_type=models.BrainRegionHierarchy
        )
        try:
            check_hierarchy_species(hierarchy, subject)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    return brain_region, subject


def _register_draft_from_uploads(  # ruff: ignore[too-many-arguments]
    *,
    db_client: entitysdk.client.Client,
    archive_path: Path,
    name: str,
    description: str,
    build_category: str,
    target_simulator: str,
    brain_region: models.BrainRegion,
    subject: models.Subject,
    scale_override: CircuitScale | None,
    contact_email: str | None,
    published_in: str | None,
    experiment_date: datetime | None,
    license_entity: models.License | None,
    atlas: models.BrainAtlas | None,
    parent_entity: models.Circuit | None,
    derivation_type: DerivationType | None,
    raw_contributions: dict[str, Any] | None,
    raw_publications: dict[str, Any] | None,
    authorized_public: bool,
    overview_image_path: Path | None,
    sim_designer_image_path: Path | None,
    dry_run: bool = False,
) -> models.Circuit:
    """Resolve optional links and register a draft circuit entity.

    When ``dry_run`` is True, validates inputs and computes circuit metadata
    without creating any entitycore records or assets.
    """
    try:
        contribution_dict = (
            get_contributions(db_client, raw_contributions) if raw_contributions else None
        )
        publication_dict = (
            get_publications(db_client, raw_publications) if raw_publications else None
        )
        registered = register_circuit(
            client=db_client,
            circuit_path=archive_path,
            name=name,
            description=description,
            build_category=build_category,  # ty:ignore[invalid-argument-type]
            brain_region=brain_region,
            subject=subject,
            target_simulator=target_simulator,  # ty:ignore[invalid-argument-type]
            scale_override=scale_override,
            contact_email=contact_email,
            published_in=published_in,
            experiment_date=experiment_date,
            license=license_entity,
            atlas=atlas,
            parent=parent_entity,
            derivation_type=derivation_type,
            contributions=contribution_dict,
            publications=publication_dict,
            authorized_public=authorized_public,
            skip_validation=True,
            lifecycle_status="draft",
            include_visualization=not dry_run,
            overview_image_path=overview_image_path,
            sim_designer_image_path=sim_designer_image_path,
            dry_run=dry_run,
            skip_additional_assets=dry_run,
        )
    except (OSError, tarfile.TarError) as e:
        raise HTTPException(
            status_code=422, detail=f"circuit_archive must be a valid .tar.gz file: {e}"
        ) from e
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if registered is None:
        raise HTTPException(status_code=500, detail="Circuit registration returned no entity")
    return registered


@router.post("/circuit/register")
def register_circuit_endpoint(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
    ls_client: LaunchSystemClientDep,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    brain_region_id: Annotated[UUID, Form()],
    subject_id: Annotated[UUID, Form()],
    build_category: Annotated[str, Form()],
    target_simulator: Annotated[str, Form()],
    circuit_archive: Annotated[UploadFile, File()],
    scale_override: Annotated[str | None, Form()] = None,
    parent_circuit_id: Annotated[UUID | None, Form()] = None,
    derivation_type: Annotated[str | None, Form()] = None,
    atlas_id: Annotated[UUID | None, Form()] = None,
    license_id: Annotated[UUID | None, Form()] = None,
    contact_email: Annotated[str | None, Form()] = None,
    published_in: Annotated[str | None, Form()] = None,
    experiment_date: Annotated[str | None, Form()] = None,
    contributions: Annotated[
        str | None,
        Form(description='JSON object: {"Agent": {"type": "person", "role": "..."}}'),
    ] = None,
    publications: Annotated[
        str | None,
        Form(description='JSON object: {"10.1234/doi": {"type": "..."}}'),
    ] = None,
    overview_image: Annotated[
        UploadFile | None, File(description="Pre-computed overview image (.png or .webp)")
    ] = None,
    sim_designer_image: Annotated[
        UploadFile | None, File(description="Pre-computed sim-designer image (.png)")
    ] = None,
    authorized_public: Annotated[bool, Form()] = False,  # ruff: ignore[boolean-default-value-positional-argument]
    dry_run: Annotated[  # ruff: ignore[boolean-default-value-positional-argument]
        bool,
        Form(description="Validate and compute metadata without registering or launching jobs"),
    ] = False,
) -> dict:
    """Register a new circuit entity with async validation.

    Thin HTTP wrapper around ``register_circuit``: creates the entity in draft
    state (skipping in-process SONATA validation), then triggers the async
    validation launch job. Large archives are unzipped on the webserver for
    metadata/assets — consider moving that off the request path if disk is tight.

    Set ``dry_run=true`` to compute circuit metadata and validate inputs without
    creating any entitycore records or triggering async validation/asset jobs.

    Optional parity with ``register_circuit_from_metadata``:
    duplicate-name check, hierarchy/species check, ``published_in``,
    ``experiment_date``, contributions/publications JSON, and image overrides.
    ``scale_override`` is already supported as a form field.
    """
    if authorized_public and license_id is None:
        raise HTTPException(status_code=422, detail="license_id required for public circuits")

    if parent_circuit_id and not derivation_type:
        raise HTTPException(
            status_code=422, detail="derivation_type required when parent_circuit_id is set"
        )

    parsed_derivation_type = _parse_optional_enum(
        derivation_type, DerivationType, "derivation_type"
    )
    parsed_scale = _parse_optional_enum(scale_override, CircuitScale, "scale_override")
    parsed_experiment_date = _parse_experiment_date(experiment_date)
    raw_contributions = _parse_json_object_form(contributions, "contributions")
    raw_publications = _parse_json_object_form(publications, "publications")

    try:
        check_if_circuit_exists(db_client, {"name": name})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # NOTE: Synchronous metadata computation requires unzipping the full circuit
        # on the webserver. Large archives may exhaust local disk space; consider
        # moving metadata computation off the request path if that becomes an issue.
        archive_path = tmp / circuit_archive.filename  # ty:ignore[unsupported-operator]
        archive_path.write_bytes(circuit_archive.file.read())

        brain_region, subject = _load_region_and_subject(
            db_client, brain_region_id=brain_region_id, subject_id=subject_id
        )
        registered = _register_draft_from_uploads(
            db_client=db_client,
            archive_path=archive_path,
            name=name,
            description=description,
            build_category=build_category,
            target_simulator=target_simulator,
            brain_region=brain_region,
            subject=subject,
            scale_override=parsed_scale,
            contact_email=contact_email,
            published_in=published_in,
            experiment_date=parsed_experiment_date,
            license_entity=_get_optional_entity(db_client, license_id, models.License),
            atlas=_get_optional_entity(db_client, atlas_id, models.BrainAtlas),
            parent_entity=_get_optional_entity(db_client, parent_circuit_id, models.Circuit),
            derivation_type=parsed_derivation_type,
            raw_contributions=raw_contributions,
            raw_publications=raw_publications,
            authorized_public=authorized_public,
            overview_image_path=_save_optional_upload(overview_image, tmp),
            sim_designer_image_path=_save_optional_upload(sim_designer_image, tmp),
            dry_run=dry_run,
        )

    if not dry_run:
        trigger_validation_task(
            ls_client=ls_client,
            circuit_id=registered.id,
            project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
            virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
        )

    number_connections = registered.number_connections
    return {
        "circuit_id": None if dry_run else str(registered.id),
        "status": "dry_run" if dry_run else "draft",
        "number_neurons": int(registered.number_neurons),
        "number_synapses": int(registered.number_synapses),
        "number_connections": int(number_connections) if number_connections is not None else None,
        "scale": str(registered.scale),
    }


@router.post("/circuit/{circuit_id}/validate")
def validate_circuit_endpoint(
    circuit_id: UUID,
    ls_client: LaunchSystemClientDep,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    force: bool = False,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
) -> dict:
    """Trigger (re-)validation for a circuit.

    By default only ``draft`` circuits are validated. Pass ``force=true`` to
    re-validate an active or disqualified circuit.
    """
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)
    status = getattr(circuit, "lifecycle_status", None)
    if not is_validation_allowed(lifecycle_status=status, force=force):
        raise HTTPException(
            status_code=409,
            detail=validation_blocked_detail(status),
        )

    trigger_validation_task(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
        virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
        force=force,
    )

    return {"circuit_id": str(circuit_id), "status": "validation_triggered"}


@router.post("/circuit/{circuit_id}/generate-assets")
def generate_assets_endpoint(
    circuit_id: UUID,
    ls_client: LaunchSystemClientDep,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    force: bool = False,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
) -> dict:
    """Trigger asset generation for an active circuit.

    Re-launchable: generates compressed circuit and connectivity matrices.
    Visualization assets are created at register/customize time and are not
    regenerated here. Does not affect readiness_status.
    """
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)

    # Only active circuits can generate assets
    if getattr(circuit, "lifecycle_status", None) not in {"active", None}:
        status = getattr(circuit, "lifecycle_status", "unknown")
        raise HTTPException(
            status_code=409,
            detail=f"Circuit lifecycle_status is '{status}'. "
            "Asset generation requires an active circuit.",
        )

    # Check if assets already exist (unless force)
    if not force:
        existing_labels = {a.label for a in (circuit.assets or [])}
        needed = {"compressed_sonata_circuit", "circuit_connectivity_matrices"}
        if needed.issubset(existing_labels):
            return {"circuit_id": str(circuit_id), "message": "all assets already exist"}

    trigger_asset_generation_task(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
        virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
        force=force,
    )

    return {"circuit_id": str(circuit_id), "status": "generation_triggered"}
