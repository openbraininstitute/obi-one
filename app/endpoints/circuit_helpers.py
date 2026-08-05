"""Shared helpers for circuit registration and customization endpoints."""

import logging
from pathlib import Path
from uuid import UUID

import entitysdk.client
import httpx
from entitysdk import models
from entitysdk.types import AssetLabel

from app.config import settings
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.utils.circuit import get_circuit_properties, get_circuit_size
from obi_one.utils.circuit_registration.generate import (
    generate_connectivity_matrix_asset,
    generate_connectivity_plot_assets,
    generate_overview_image_asset,
    generate_sim_designer_image_asset,
)

L = logging.getLogger(__name__)


def compute_circuit_metadata(
    name: str, config_path: Path
) -> tuple["OBICircuit", str, int, int, int | None, bool, bool, bool, bool]:
    """Load a circuit from config and compute its metadata.

    Returns:
        Tuple of (circuit_obj, scale, number_neurons, number_synapses,
        number_connections, has_morphologies, has_point_neurons,
        has_electrical_cell_models, has_spines).
    """
    c = OBICircuit(name=name, path=str(config_path))
    scale, number_neurons, number_synapses, number_connections = get_circuit_size(c)
    has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
        get_circuit_properties(c)
    )
    return (
        c,
        scale,
        number_neurons,
        number_synapses,
        number_connections,
        has_morphologies,
        has_point_neurons,
        has_electrical_cell_models,
        has_spines,
    )


def upload_sonata_circuit(
    db_client: entitysdk.client.Client,
    registered: models.Circuit,
    circuit_dir: Path,
) -> None:
    """Upload all files in circuit_dir as the sonata_circuit directory asset."""
    paths = {p.relative_to(circuit_dir): p for p in circuit_dir.rglob("*") if p.is_file()}
    db_client.upload_directory(
        entity_id=registered.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.Circuit,
        name="sonata_circuit",
        paths=paths,  # ty:ignore[invalid-argument-type]
        label=AssetLabel.sonata_circuit,
    )


def generate_and_register_visualization_assets(
    circuit: OBICircuit,
    config_path: Path,
    output_root: Path,
    db_client: entitysdk.client.Client,
    registered: models.Circuit,
) -> None:
    """Generate connectivity matrix, plots, and overview images for a circuit.

    Skips silently if the circuit has no edge populations.
    """
    edge_pop = (
        circuit.default_edge_population_name
        if circuit.sonata_circuit.edges.population_names
        else None
    )
    if edge_pop is None:
        return

    matrix_dir = output_root / "__CONN_MATRIX__"
    plot_dir = output_root / "__BASIC_PLOTS__"
    viz_dir = output_root / "__CIRCUIT_VIZ__"

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


def trigger_validation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    force: bool = False,
) -> None:
    """Submit a circuit validation job to the launch-system.

    Args:
        force: Forwarded to the job. When True, validate even if the circuit
            is not in ``draft`` lifecycle status.
    """
    launch_path = "launch_scripts/launch_circuit_validation"
    asset_gen_callback = {
        "action_type": "http_request_with_token",
        "event_type": "job_on_success",
        "config": {
            "url": (
                f"{settings.API_URL}/api/obi-one/declared/circuit"
                f"/{circuit_id}/generate-assets"
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
            "image_type": "obi_one",
            "cores": 1,
            "memory": 8,
            "timelimit": "00:30",
            "compute_cell": "local",
        },
        "inputs": [
            f"--circuit_id {circuit_id}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
            f"--force {str(force).lower()}",
        ],
        "project_id": str(project_id),
        "callbacks": [asset_gen_callback],
    }

    response = ls_client.post(url="/job", json=job_data)
    if response.is_success:
        L.info("Validation task submitted for circuit %s", circuit_id)
    else:
        L.warning("Failed to submit validation task for circuit %s: %s", circuit_id, response.text)


def trigger_asset_generation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    force: bool = False,
) -> None:
    """Submit an asset generation job to the launch-system.

    Args:
        force: Forwarded to the job. When True, compressed archive is regenerated
            even if ``compressed_sonata_circuit`` already exists on the entity.
    """
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
            "cores": 1,
            "memory": 16,
            "timelimit": "01:00",
            "compute_cell": "local",
        },
        "inputs": [
            f"--circuit_id {circuit_id}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
            f"--force {str(force).lower()}",
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
