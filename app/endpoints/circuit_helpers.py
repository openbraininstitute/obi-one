"""Shared helpers for circuit registration and customization endpoints."""

import logging
from pathlib import Path
from uuid import UUID

import entitysdk.client
import httpx
from entitysdk import models
from entitysdk.types import AssetLabel, CircuitScale

from app.config import settings
from obi_one.db_sdk.registration.circuit.generate import (
    generate_connectivity_matrix_asset,
    generate_connectivity_plot_assets,
    generate_overview_image_asset,
    generate_sim_designer_image_asset,
)
from obi_one.db_sdk.registration.circuit.launch_jobs import (
    submit_circuit_asset_generation_job,
    submit_circuit_validation_job,
)
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.utils.circuit import get_circuit_properties, get_circuit_size

L = logging.getLogger(__name__)


def compute_circuit_metadata(
    name: str, config_path: Path
) -> tuple["OBICircuit", CircuitScale, int, int, int | None, bool, bool, bool, bool]:
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
        entity_id=registered.id,
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
        ls_client: Launch-system HTTP client.
        circuit_id: Circuit entity ID to validate.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        force: When True, validate even if the circuit is not in ``draft`` status.
    """
    submit_circuit_validation_job(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        api_url=settings.API_URL,
        obi_one_repo=settings.OBI_ONE_REPO,
        app_version=settings.APP_VERSION,
        force=force,
    )


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
        ls_client: Launch-system HTTP client.
        circuit_id: Circuit entity ID to generate assets for.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        force: When True, regenerate compressed archive even if it already exists.
    """
    submit_circuit_asset_generation_job(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        obi_one_repo=settings.OBI_ONE_REPO,
        app_version=settings.APP_VERSION,
        force=force,
    )
