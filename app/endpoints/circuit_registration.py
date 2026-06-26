"""Circuit registration endpoint."""

import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
import httpx
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType, DerivationType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import settings
from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.utils.circuit import get_circuit_properties, get_circuit_size

L = logging.getLogger(__name__)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post("/circuit/register")
def register_circuit_endpoint(  # noqa: PLR0913, PLR0917, PLR0914
    ls_client: LaunchSystemClientDep,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    brain_region_id: Annotated[UUID, Form()],
    subject_id: Annotated[UUID, Form()],
    build_category: Annotated[str, Form()],
    target_simulator: Annotated[str, Form()],
    circuit_archive: Annotated[UploadFile, File()],
    scale_override: Annotated[str | None, Form()] = None,  # noqa: ARG001
    parent_circuit_id: Annotated[UUID | None, Form()] = None,
    derivation_type: Annotated[str | None, Form()] = None,
    atlas_id: Annotated[UUID | None, Form()] = None,
    license_id: Annotated[UUID | None, Form()] = None,
    contact_email: Annotated[str | None, Form()] = None,
    authorized_public: Annotated[bool, Form()] = False,  # noqa: FBT002
) -> dict:
    """Register a new circuit entity with async validation.

    Uploads the circuit, computes metadata synchronously, creates the entity
    in draft state, and triggers an async validation task.
    """
    if authorized_public and license_id is None:
        raise HTTPException(status_code=422, detail="license_id required for public circuits")

    if parent_circuit_id and not derivation_type:
        raise HTTPException(
            status_code=422, detail="derivation_type required when parent_circuit_id is set"
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # 1. Extract archive
        archive_path = tmp / circuit_archive.filename
        archive_path.write_bytes(circuit_archive.file.read())
        circuit_dir = _extract_archive(archive_path, tmp)

        # 2. Locate circuit_config.json
        config_path = circuit_dir / "circuit_config.json"
        if not config_path.exists():
            # Try one level down
            subdirs = [d for d in circuit_dir.iterdir() if d.is_dir()]
            for sd in subdirs:
                if (sd / "circuit_config.json").exists():
                    circuit_dir = sd
                    config_path = sd / "circuit_config.json"
                    break
            if not config_path.exists():
                raise HTTPException(
                    status_code=422, detail="circuit_config.json not found in archive"
                )

        # 3. Compute metadata
        c = OBICircuit(name=name, path=str(config_path))
        scale, number_neurons, number_synapses, number_connections = get_circuit_size(c)
        has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
            get_circuit_properties(c)
        )

        # 4. Resolve entities
        brain_region = db_client.get_entity(
            entity_id=brain_region_id, entity_type=models.BrainRegion
        )
        subject = db_client.get_entity(entity_id=subject_id, entity_type=models.Subject)

        # 5. Create circuit entity
        circuit_model = models.Circuit(
            name=name,
            description=description,
            subject=subject,
            brain_region=brain_region,
            number_neurons=number_neurons,
            number_synapses=number_synapses,
            number_connections=number_connections,
            has_morphologies=has_morphologies,
            has_point_neurons=has_point_neurons,
            has_electrical_cell_models=has_electrical_cell_models,
            has_spines=has_spines,
            scale=scale,
            build_category=build_category,
            target_simulator=target_simulator,
            root_circuit_id=parent_circuit_id,
            atlas_id=atlas_id,
        )
        registered = db_client.register_entity(circuit_model)
        L.info("Circuit '%s' registered as %s (draft)", registered.name, registered.id)

        # 6. Upload sonata_circuit asset
        paths = {
            p.relative_to(circuit_dir): p for p in circuit_dir.rglob("*") if p.is_file()
        }
        db_client.upload_directory(
            entity_id=registered.id,
            entity_type=models.Circuit,
            name="sonata_circuit",
            paths=paths,
            label=AssetLabel.sonata_circuit,
        )

        # 6b. Upload original archive as compressed_sonata_circuit (skips compression stage)
        db_client.upload_file(
            entity_id=registered.id,
            entity_type=models.Circuit,
            file_path=archive_path,
            file_content_type=ContentType.application_gzip,
            asset_label=AssetLabel.compressed_sonata_circuit,
        )

        # 6c. Generate and register stats + visualization assets
        edge_pop = (
            c.default_edge_population_name if c.sonata_circuit.edges.population_names else None
        )
        if edge_pop is not None:
            from obi_one.utils.circuit_registration.generate import (
                generate_connectivity_matrix_asset,
                generate_connectivity_plot_assets,
                generate_overview_image_asset,
                generate_sim_designer_image_asset,
            )

            matrix_dir = config_path.parent / "__CONN_MATRIX__"
            plot_dir = config_path.parent / "__BASIC_PLOTS__"
            viz_dir = config_path.parent / "__CIRCUIT_VIZ__"

            _, matrix_config, edge_pop = generate_connectivity_matrix_asset(
                circuit_path=config_path,
                output_dir=matrix_dir,
                edge_population=edge_pop,
            )

            generate_connectivity_plot_assets(
                matrix_config=matrix_config,
                edge_population=edge_pop,
                output_dir=plot_dir,
                client=db_client,
                circuit_entity=registered,
            )

            generate_overview_image_asset(
                plot_dir=plot_dir,
                output_dir=viz_dir,
                client=db_client,
                circuit_entity=registered,
            )

            generate_sim_designer_image_asset(
                plot_dir=plot_dir,
                output_dir=viz_dir,
                client=db_client,
                circuit_entity=registered,
            )

    # 7. Trigger validation task
    _trigger_validation_task(
        ls_client=ls_client,
        circuit_id=registered.id,
        project_id=db_client.project_context.project_id,
        virtual_lab_id=db_client.project_context.virtual_lab_id,
    )

    return {
        "circuit_id": str(registered.id),
        "status": "draft",
        "number_neurons": int(number_neurons),
        "number_synapses": int(number_synapses),
        "number_connections": int(number_connections) if number_connections is not None else None,
        "scale": str(scale),
    }


@router.post("/circuit/{circuit_id}/generate-assets")
def generate_assets_endpoint(
    circuit_id: UUID,
    ls_client: LaunchSystemClientDep,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    force: bool = False,  # noqa: FBT001, FBT002
) -> dict:
    """Trigger asset generation for an active circuit.

    Re-launchable: generates compressed circuit, connectivity matrices,
    stats, and images. Does not affect readiness_status.
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

    _trigger_asset_generation_task(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=db_client.project_context.project_id,
        virtual_lab_id=db_client.project_context.virtual_lab_id,
    )

    return {"circuit_id": str(circuit_id), "status": "generation_triggered"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_archive(archive_path: Path, dest: Path) -> Path:
    """Extract a .tar.gz archive and return the extracted directory."""
    extract_dir = dest / "circuit"
    extract_dir.mkdir()

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tar:
            tar.extractall(path=extract_dir, filter="data")
    else:
        raise HTTPException(status_code=422, detail="circuit_archive must be a .tar.gz file")

    return extract_dir


def _trigger_validation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
) -> None:
    """Submit a circuit validation job to the launch-system."""
    launch_path = "launch_scripts/launch_circuit_validation"
    asset_gen_callback = {
        "action_type": "http_request_with_token",
        "event_type": "job_on_success",
        "config": {
            "url": (
                f"{settings.API_URL}/api/obi-one/declared/circuit"
                f"/{circuit_id}/generate-assets?force=true"
            ),
            "method": "POST",
        },
    }
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}",
            "path": f"{launch_path}/main.py",
            "dependencies": f"{launch_path}/dependencies/default.txt",
        },
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 8,
            "timelimit": "00:30",
            "compute_cell": "local",
        },
        "inputs": [
            f"--circuit_id {circuit_id}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
        ],
        "project_id": str(project_id),
        "callbacks": [asset_gen_callback],
    }

    response = ls_client.post(url="/job", json=job_data)
    if response.is_success:
        L.info("Validation task submitted for circuit %s", circuit_id)
    else:
        L.warning("Failed to submit validation task for circuit %s: %s", circuit_id, response.text)


def _trigger_asset_generation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
) -> None:
    """Submit an asset generation job to the launch-system."""
    launch_path = "launch_scripts/launch_circuit_asset_generation"
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}",
            "path": f"{launch_path}/main.py",
            "dependencies": f"{launch_path}/dependencies/default.txt",
        },
        "resources": {
            "type": "machine",
            "cores": 2,
            "memory": 16,
            "timelimit": "01:00",
            "compute_cell": "local",
        },
        "inputs": [
            f"--circuit_id {circuit_id}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
        ],
        "project_id": str(project_id),
        "callbacks": [],
    }

    response = ls_client.post(url="/job", json=job_data)
    if response.is_success:
        L.info("Asset generation task submitted for circuit %s", circuit_id)
    else:
        L.warning(
            "Failed to submit asset generation task for circuit %s: %s", circuit_id, response.text
        )
