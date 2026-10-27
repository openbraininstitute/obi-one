"""Shared helpers for circuit registration and customization endpoints."""

import logging
from http import HTTPStatus
from uuid import UUID

import httpx
from entitysdk import models
from entitysdk.types import CircuitScale, EntityType

from app.config import settings
from app.errors import ApiError, ApiErrorCode
from app.schemas.task import AfterSuccess
from obi_one.db_sdk.registration.circuit.generate import missing_assets
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
) -> UUID | None:
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

    Returns:
        Launch-system job ID if accepted, otherwise ``None``.
    """
    return submit_circuit_validation_job(
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
    scale: CircuitScale | None,
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
    force: bool = False,
) -> UUID | None:
    """Submit an asset generation job to the launch-system.

    Args:
        ls_client: Launch-system HTTP client.
        circuit_id: Circuit entity ID to generate assets for.
        scale: The circuit's scale, which sizes the job's machine.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        compute_cell: Compute cell for the launch-system job (from the vlab).
        force: When True, regenerate compressed archive even if it already exists.

    Returns:
        Launch-system job ID if accepted, otherwise ``None``.
    """
    return submit_circuit_asset_generation_job(
        ls_client=ls_client,
        circuit_id=circuit_id,
        scale=scale,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        compute_cell=compute_cell,
        obi_one_repo=settings.OBI_ONE_REPO,
        app_version=settings.APP_VERSION,
        force=force,
    )


def build_missing_circuit_assets(done: AfterSuccess) -> None:
    """Have the asset job build the assets each circuit the task generated lacks: for a task whose
    machine is too small to build every asset itself.
    """
    circuits = [
        done.db_client.get_entity(entity_id=entity.id, entity_type=models.Circuit)
        for entity in done.activity.generated or []
        if entity.type == EntityType.circuit
    ]
    if not circuits:
        L.warning("Task activity %s generated no circuit to build the assets of", done.activity.id)
    refused = []
    for circuit in circuits:
        if not missing_assets(circuit):
            L.info("Circuit %s has every asset the asset job builds", circuit.id)
            continue
        job_id = trigger_asset_generation_task(
            ls_client=done.ls_client,
            circuit_id=circuit.id,
            scale=circuit.scale,
            project_id=done.project_id,
            virtual_lab_id=done.virtual_lab_id,
            compute_cell=done.compute_cell,
        )
        if job_id is None:
            refused.append(str(circuit.id))
    if refused:
        raise ApiError(
            message=f"Failed to submit the asset job of circuits {', '.join(refused)}",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=ApiErrorCode.INTERNAL_ERROR,
        )
