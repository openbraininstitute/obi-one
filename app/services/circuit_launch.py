"""Launch-system jobs for circuit validation and asset generation."""

import logging
from uuid import UUID

import entitysdk.client
import httpx
from entitysdk.models import Entity
from entitysdk.types import EntityLifecycleStatus

from app.config import settings
from app.errors import internal_error
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
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
    force: bool = False,
) -> UUID | None:
    """Submit an asset generation job to the launch-system.

    Args:
        ls_client: Launch-system HTTP client.
        circuit_id: Circuit entity ID to generate assets for.
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
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        compute_cell=compute_cell,
        obi_one_repo=settings.OBI_ONE_REPO,
        app_version=settings.APP_VERSION,
        force=force,
    )


def validate_draft_circuits(
    *,
    entities: list[Entity],
    db_client: entitysdk.client.Client,
    ls_client: httpx.Client,
    compute_cell: str,
) -> None:
    """Start a validation job for each draft circuit a task generated.

    This is the handler for generated circuits (``app.services.generated_entities``). Circuits
    that are not drafts are skipped. Every draft gets one try; if any submission fails, the
    function raises at the end, so the launch-system retries the callback instead of leaving a
    draft that is never validated. On a retry, drafts whose job was already started get a
    second job. That is harmless, and it can only happen when an activity has several circuits
    (today each task registers one).

    Args:
        entities: Circuits the task activity generated.
        db_client: EntitySDK client with the task's project context.
        ls_client: Launch-system HTTP client.
        compute_cell: Compute cell for the validation jobs (from the virtual lab).
    """
    failed_circuit_ids: list[UUID] = []
    for circuit in entities:
        if circuit.lifecycle_status != EntityLifecycleStatus.draft:
            continue
        job_id = trigger_validation_task(
            ls_client=ls_client,
            circuit_id=circuit.id,
            project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
            virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            compute_cell=compute_cell,
        )
        if job_id is None:
            failed_circuit_ids.append(circuit.id)
    if failed_circuit_ids:
        msg = f"Failed to submit the validation job for circuits {failed_circuit_ids}."
        raise internal_error(msg)
