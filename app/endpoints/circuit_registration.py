"""Circuit registration endpoint."""

import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
from entitysdk import models
from entitysdk.types import CircuitScale, DerivationType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.circuit_helpers import trigger_asset_generation_task, trigger_validation_task
from obi_one.utils.circuit_registration import register_circuit

L = logging.getLogger(__name__)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post("/circuit/register")
def register_circuit_endpoint(  # noqa: PLR0913, PLR0917, C901
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
    authorized_public: Annotated[bool, Form()] = False,  # noqa: FBT002
) -> dict:
    """Register a new circuit entity with async validation.

    Thin HTTP wrapper around ``register_circuit``: creates the entity in draft
    state (skipping in-process SONATA validation), then triggers the async
    validation launch job. Large archives are unzipped on the webserver for
    metadata/assets — consider moving that off the request path if disk is tight.
    """
    if authorized_public and license_id is None:
        raise HTTPException(status_code=422, detail="license_id required for public circuits")

    if parent_circuit_id and not derivation_type:
        raise HTTPException(
            status_code=422, detail="derivation_type required when parent_circuit_id is set"
        )

    parsed_derivation_type: DerivationType | None = None
    if derivation_type is not None:
        try:
            parsed_derivation_type = DerivationType(derivation_type)
        except ValueError as e:
            raise HTTPException(
                status_code=422, detail=f"Invalid derivation_type '{derivation_type}'"
            ) from e

    parsed_scale: CircuitScale | None = None
    if scale_override is not None:
        try:
            parsed_scale = CircuitScale(scale_override)
        except ValueError as e:
            raise HTTPException(
                status_code=422, detail=f"Invalid scale_override '{scale_override}'"
            ) from e

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # 1. Extract archive
        # NOTE: Synchronous metadata computation requires unzipping the full circuit
        # on the webserver. Large archives may exhaust local disk space; consider
        # moving metadata computation off the request path if that becomes an issue.
        archive_path = tmp / circuit_archive.filename  # ty:ignore[unsupported-operator]
        archive_path.write_bytes(circuit_archive.file.read())

        brain_region = db_client.get_entity(
            entity_id=brain_region_id, entity_type=models.BrainRegion
        )
        subject = db_client.get_entity(entity_id=subject_id, entity_type=models.Subject)

        license_entity = None
        if license_id is not None:
            license_entity = db_client.get_entity(entity_id=license_id, entity_type=models.License)

        atlas = None
        if atlas_id is not None:
            atlas = db_client.get_entity(entity_id=atlas_id, entity_type=models.BrainAtlas)

        parent_entity = None
        if parent_circuit_id is not None:
            parent_entity = db_client.get_entity(
                entity_id=parent_circuit_id, entity_type=models.Circuit
            )

        try:
            registered = register_circuit(
                client=db_client,
                circuit_path=archive_path,
                name=name,
                description=description,
                build_category=build_category,  # ty:ignore[invalid-argument-type]
                brain_region=brain_region,
                subject=subject,
                target_simulator=target_simulator,  # ty:ignore[invalid-argument-type]
                scale_override=parsed_scale,
                contact_email=contact_email,
                license=license_entity,
                atlas=atlas,
                parent=parent_entity,
                derivation_type=parsed_derivation_type,
                authorized_public=authorized_public,
                skip_validation=True,
                lifecycle_status="draft",
                include_visualization=True,
            )
        except (OSError, tarfile.TarError) as e:
            raise HTTPException(
                status_code=422, detail=f"circuit_archive must be a valid .tar.gz file: {e}"
            ) from e
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    if registered is None:
        raise HTTPException(status_code=500, detail="Circuit registration returned no entity")

    trigger_validation_task(
        ls_client=ls_client,
        circuit_id=registered.id,  # ty:ignore[invalid-argument-type]
        project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
        virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
    )

    number_connections = registered.number_connections
    return {
        "circuit_id": str(registered.id),
        "status": "draft",
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
    force: bool = False,  # noqa: FBT001, FBT002
) -> dict:
    """Trigger (re-)validation for a circuit.

    By default only ``draft`` circuits are validated. Pass ``force=true`` to
    re-validate an active or disqualified circuit.
    """
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)
    status = getattr(circuit, "lifecycle_status", None)
    if not force and status is not None and str(status) != "draft":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Circuit lifecycle_status is '{status}'. "
                "Validation requires draft status, or pass force=true to overwrite."
            ),
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
    force: bool = False,  # noqa: FBT001, FBT002
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
