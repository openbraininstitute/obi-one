"""Launch-system job submission for circuit validation and asset generation."""

import logging
from pathlib import Path
from uuid import UUID

import httpx

from app.dependencies.constraints import build_obi_one_constraint_from_file

L = logging.getLogger(__name__)

DEFAULT_OBI_ONE_REPO = "https://github.com/openbraininstitute/obi-one.git"
VALIDATION_LAUNCH_PATH = "launch_scripts/launch_circuit_validation"
ASSET_GENERATION_LAUNCH_PATH = "launch_scripts/launch_circuit_asset_generation"
VALIDATION_IMAGE_TYPE = "python_3_12_openmpi5_neuron9_neurodamus"

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _app_tag(app_version: str | None) -> str:
    return (app_version or "0.0.0").split("-")[0]


def submit_circuit_validation_job(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    api_url: str,
    compute_cell: str,
    obi_one_repo: str = DEFAULT_OBI_ONE_REPO,
    app_version: str | None = None,
    force: bool = False,
    generate_assets_on_success: bool = True,
) -> bool:
    """Submit a circuit validation job to the launch-system.

    The job runs on ``python_3_12_openmpi5_neuron9_neurodamus``, stages the
    circuit, compiles MOD files, runs snap validation, and updates lifecycle
    status. When ``generate_assets_on_success`` is True, a successful run
    callbacks to the generate-assets HTTP endpoint.

    Args:
        ls_client: Launch-system HTTP client (authenticated).
        circuit_id: Circuit entity ID to validate.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        api_url: Base URL of the obi-one API, already including the ``/api/obi-one``
            path prefix (e.g. ``https://staging.cell-a.openbraininstitute.org/api/obi-one``);
            used to build the generate-assets callback URL.
        compute_cell: Compute cell for the launch-system job (from the vlab).
        obi_one_repo: Git repository URL for the launch script checkout.
        app_version: App version used to form ``tag:<version>``; defaults to ``0.0.0``.
        force: When True, validate even if the circuit is not in ``draft`` status.
        generate_assets_on_success: When True, trigger asset generation after a
            successful validation. Disable for standalone re-validation.

    Returns:
        True if the launch-system accepted the job, False otherwise.
    """
    callbacks = []
    if generate_assets_on_success:
        callbacks.append(
            {
                "action_type": "http_request_with_token",
                "event_type": "job_on_success",
                "config": {
                    "url": (f"{api_url}/declared/circuit/{circuit_id}/generate-assets"),
                    "method": "POST",
                },
            }
        )
    job_data = {
        "code": {
            "type": "python_repository",
            "location": obi_one_repo,
            "ref": f"tag:{_app_tag(app_version)}",
            "path": f"{VALIDATION_LAUNCH_PATH}/main.py",
            "dependencies": f"{VALIDATION_LAUNCH_PATH}/dependencies/default.txt",
            "dependency_constraints": build_obi_one_constraint_from_file(
                app_version,
                _REPO_ROOT / VALIDATION_LAUNCH_PATH / "dependencies" / "default.txt",
            ),
        },
        "resources": {
            "type": "machine",
            "image_type": VALIDATION_IMAGE_TYPE,
            "cores": 1,
            "memory": 8,
            "timelimit": "00:30",
            "compute_cell": compute_cell,
        },
        "inputs": [
            f"--circuit_id {circuit_id}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
            f"--force {str(force).lower()}",
        ],
        "project_id": str(project_id),
        "callbacks": callbacks,
    }

    response = ls_client.post(url="/job", json=job_data)
    if response.is_success:
        L.info("Validation task submitted for circuit %s", circuit_id)
        return True

    L.warning("Failed to submit validation task for circuit %s: %s", circuit_id, response.text)
    return False


def submit_circuit_asset_generation_job(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
    obi_one_repo: str = DEFAULT_OBI_ONE_REPO,
    app_version: str | None = None,
    force: bool = False,
) -> bool:
    """Submit a circuit asset-generation job to the launch-system.

    Stages the circuit and generates compressed SONATA + connectivity matrices.
    Visualization assets are expected to already exist from registration.

    Args:
        ls_client: Launch-system HTTP client (authenticated).
        circuit_id: Circuit entity ID to generate assets for.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        compute_cell: Compute cell for the launch-system job (from the vlab).
        obi_one_repo: Git repository URL for the launch script checkout.
        app_version: App version used to form ``tag:<version>``; defaults to ``0.0.0``.
        force: When True, regenerate compressed archive even if it already exists.

    Returns:
        True if the launch-system accepted the job, False otherwise.
    """
    job_data = {
        "code": {
            "type": "python_repository",
            "location": obi_one_repo,
            "ref": f"tag:{_app_tag(app_version)}",
            "path": f"{ASSET_GENERATION_LAUNCH_PATH}/main.py",
            "dependencies": f"{ASSET_GENERATION_LAUNCH_PATH}/dependencies/default.txt",
            "dependency_constraints": build_obi_one_constraint_from_file(
                app_version,
                _REPO_ROOT / ASSET_GENERATION_LAUNCH_PATH / "dependencies" / "default.txt",
            ),
        },
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 16,
            "timelimit": "01:00",
            "compute_cell": compute_cell,
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
        return True

    L.warning(
        "Failed to submit asset generation task for circuit %s: %s", circuit_id, response.text
    )
    return False
