"""Launch-system job submission for async circuit validation."""

import logging
from uuid import UUID

import httpx

L = logging.getLogger(__name__)

DEFAULT_OBI_ONE_REPO = "https://github.com/openbraininstitute/obi-one.git"
VALIDATION_LAUNCH_PATH = "launch_scripts/launch_circuit_validation"
VALIDATION_IMAGE_TYPE = "python_3_12_openmpi5_neuron9_neurodamus"


def submit_circuit_validation_job(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    api_url: str,
    obi_one_repo: str = DEFAULT_OBI_ONE_REPO,
    app_version: str | None = None,
    force: bool = False,
) -> bool:
    """Submit a circuit validation job to the launch-system.

    The job runs on ``python_3_12_openmpi5_neuron9_neurodamus``, stages the
    circuit, compiles MOD files, runs snap validation, and updates lifecycle
    status. On success it callbacks to the generate-assets HTTP endpoint.

    Args:
        ls_client: Launch-system HTTP client (authenticated).
        circuit_id: Circuit entity ID to validate.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        api_url: Base URL of the obi-one API (for the generate-assets callback).
        obi_one_repo: Git repository URL for the launch script checkout.
        app_version: App version used to form ``tag:<version>``; defaults to ``0.0.0``.
        force: When True, validate even if the circuit is not in ``draft`` status.

    Returns:
        True if the launch-system accepted the job, False otherwise.
    """
    version = (app_version or "0.0.0").split("-")[0]
    asset_gen_callback = {
        "action_type": "http_request_with_token",
        "event_type": "job_on_success",
        "config": {
            "url": f"{api_url}/api/obi-one/declared/circuit/{circuit_id}/generate-assets",
            "method": "POST",
        },
    }
    job_data = {
        "code": {
            "type": "python_repository",
            "location": obi_one_repo,
            "ref": f"tag:{version}",
            "path": f"{VALIDATION_LAUNCH_PATH}/main.py",
            "dependencies": f"{VALIDATION_LAUNCH_PATH}/dependencies/default.txt",
        },
        "resources": {
            "type": "machine",
            "image_type": VALIDATION_IMAGE_TYPE,
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
        return True

    L.warning("Failed to submit validation task for circuit %s: %s", circuit_id, response.text)
    return False
