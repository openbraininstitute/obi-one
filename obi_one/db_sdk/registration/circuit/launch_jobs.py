"""Launch-system job submission for circuit validation and asset generation."""

import logging
from uuid import UUID

import httpx
from entitysdk.types import CircuitScale

from obi_one.utils.versions import release_tag_ref

L = logging.getLogger(__name__)

DEFAULT_OBI_ONE_REPO = "https://github.com/openbraininstitute/obi-one.git"
VALIDATION_LAUNCH_PATH = "launch_scripts/launch_circuit_validation"
ASSET_GENERATION_LAUNCH_PATH = "launch_scripts/launch_circuit_asset_generation"
VALIDATION_IMAGE_TYPE = "python_3_12_openmpi5_neuron9_neurodamus"
# The asset job's placement for each compute cell, as the tasks' (app/mappings.py): on cell A,
# Fargate, whose executors mount the public data the job's client reads in place.
ASSET_GENERATION_PLACEMENTS = {"cell_a": "fargate", "cell_b": "azure_container_apps"}
# The asset job's cores and memory (GB) for each circuit scale, among the launch-system's
# combinations. Past a microcircuit the morphology pack decides the memory: about 100 bytes a
# segment, so 30 GB holds FlyWire's whole brain (about 255M segments).
ASSET_GENERATION_RESOURCES = {
    CircuitScale.single: (1, 4),
    CircuitScale.pair: (1, 4),
    CircuitScale.small: (1, 4),
    CircuitScale.microcircuit: (2, 16),
    CircuitScale.region: (4, 30),
    CircuitScale.system: (4, 30),
    CircuitScale.whole_brain: (4, 30),
}


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
) -> UUID | None:
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
        Launch-system job ID if the job was accepted, otherwise ``None``.
        The job ID can be used with ``GET /declared/task/{job_id}`` and
        ``GET /declared/task/{job_id}/stream`` to inspect status and logs.
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
                    "headers": {
                        "virtual-lab-id": str(virtual_lab_id),
                        "project-id": str(project_id),
                    },
                },
            }
        )
    job_data = {
        "code": {
            "type": "python_repository",
            "location": obi_one_repo,
            "ref": release_tag_ref(app_version),
            "path": f"{VALIDATION_LAUNCH_PATH}/main.py",
            "dependencies": f"{VALIDATION_LAUNCH_PATH}/dependencies/default.txt",
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
        job_id = UUID(response.json()["id"])
        L.info("Validation task submitted for circuit %s (job_id=%s)", circuit_id, job_id)
        return job_id

    L.warning("Failed to submit validation task for circuit %s: %s", circuit_id, response.text)
    return None


def submit_circuit_asset_generation_job(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    scale: CircuitScale | None,
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
    obi_one_repo: str = DEFAULT_OBI_ONE_REPO,
    app_version: str | None = None,
    force: bool = False,
) -> UUID | None:
    """Submit a circuit asset-generation job to the launch-system.

    Stages the circuit and generates the compressed SONATA circuit, connectivity
    matrices and plots, the overview / sim-designer images (skipping any image the
    user already uploaded at registration time) and the morphology pack, on a
    machine sized for the circuit's scale.

    Args:
        ls_client: Launch-system HTTP client (authenticated).
        circuit_id: Circuit entity ID to generate assets for.
        scale: The circuit's scale, which sizes the machine; a microcircuit's where None.
        project_id: Project ID for the job.
        virtual_lab_id: Virtual lab ID for the job.
        compute_cell: Compute cell for the launch-system job (from the vlab).
        obi_one_repo: Git repository URL for the launch script checkout.
        app_version: App version used to form ``tag:<version>``; defaults to ``0.0.0``.
        force: When True, regenerate compressed archive even if it already exists.

    Returns:
        Launch-system job ID if the job was accepted, otherwise ``None``.
        The job ID can be used with ``GET /declared/task/{job_id}`` and
        ``GET /declared/task/{job_id}/stream`` to inspect status and logs.
    """
    cores, memory = ASSET_GENERATION_RESOURCES[scale or CircuitScale.microcircuit]
    job_data = {
        "code": {
            "type": "python_repository",
            "location": obi_one_repo,
            "ref": release_tag_ref(app_version),
            "path": f"{ASSET_GENERATION_LAUNCH_PATH}/main.py",
            "dependencies": f"{ASSET_GENERATION_LAUNCH_PATH}/dependencies/default.txt",
        },
        "resources": {
            "type": "machine",
            "cores": cores,
            "memory": memory,
            "timelimit": "01:00",
            "compute_cell": compute_cell,
            "placement_type": ASSET_GENERATION_PLACEMENTS.get(compute_cell),
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
        job_id = UUID(response.json()["id"])
        L.info("Asset generation task submitted for circuit %s (job_id=%s)", circuit_id, job_id)
        return job_id

    L.warning(
        "Failed to submit asset generation task for circuit %s: %s", circuit_id, response.text
    )
    return None
