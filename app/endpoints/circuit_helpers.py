"""Shared helpers for circuit registration and customization endpoints."""

import logging
from uuid import UUID

import httpx

from app.config import settings
from obi_one.db_sdk.registration.circuit.launch_jobs import (
    submit_circuit_asset_generation_job,
    submit_circuit_validation_job,
)

L = logging.getLogger(__name__)


def trigger_validation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
    force: bool = False,
    generate_assets_on_success: bool = True,
) -> None:
    """Submit a circuit validation job to the launch-system.

    Args:
        ls_client: Launch-system HTTP client.
        circuit_id: Circuit entity ID to validate.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        compute_cell: Compute cell for the launch-system job (from the vlab).
        force: When True, validate even if the circuit is not in ``draft`` status.
        generate_assets_on_success: When True, trigger asset generation after a
            successful validation. Disable for standalone re-validation.
    """
    submit_circuit_validation_job(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        api_url=settings.API_URL,
        compute_cell=compute_cell,
        obi_one_repo=settings.OBI_ONE_REPO,
        app_version=settings.APP_VERSION,
        force=force,
        generate_assets_on_success=generate_assets_on_success,
    )


def trigger_asset_generation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
    force: bool = False,
) -> None:
    """Submit an asset generation job to the launch-system.

    Args:
        ls_client: Launch-system HTTP client.
        circuit_id: Circuit entity ID to generate assets for.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        compute_cell: Compute cell for the launch-system job (from the vlab).
        force: When True, regenerate compressed archive even if it already exists.
    """
    submit_circuit_asset_generation_job(
        ls_client=ls_client,
        circuit_id=circuit_id,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        compute_cell=compute_cell,
        obi_one_repo=settings.OBI_ONE_REPO,
        app_version=settings.APP_VERSION,
        force=force,
    )
