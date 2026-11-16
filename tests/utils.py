import shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent / "test_data"
EXAMPLES_DIR = Path(__file__).parents[1] / "examples"
CIRCUIT_DIR = EXAMPLES_DIR / "data" / "tiny_circuits"
SINGLE_NEURON_CIRCUIT_DIR = EXAMPLES_DIR / "data" / "single_neuron_circuits"
MATRIX_DIR = EXAMPLES_DIR / "data" / "connectivity_matrices"

VIRTUAL_LAB_ID = "9c6fba01-2c6f-4eac-893f-f0dc665605c5"
PROJECT_ID = "ee86d4a0-eaca-48ca-9788-ddc450250b15"
UNRELATED_VIRTUAL_LAB_ID = "99999999-2c6f-4eac-893f-f0dc665605c5"
UNRELATED_PROJECT_ID = "66666666-eaca-48ca-9788-ddc450250b15"

TOKEN_ADMIN = "I'm admin"  # ruff: ignore[hardcoded-password-string]
TOKEN_USER_1 = "I'm user 1"  # ruff: ignore[hardcoded-password-string]
TOKEN_USER_2 = "I'm user 2"  # ruff: ignore[hardcoded-password-string]

AUTH_HEADER_ADMIN = {"Authorization": f"Bearer {TOKEN_ADMIN}"}
AUTH_HEADER_USER_1 = {"Authorization": f"Bearer {TOKEN_USER_1}"}
AUTH_HEADER_USER_2 = {"Authorization": f"Bearer {TOKEN_USER_2}"}

PROJECT_HEADERS = {
    "virtual-lab-id": VIRTUAL_LAB_ID,
    "project-id": PROJECT_ID,
}
UNRELATED_PROJECT_HEADERS = {
    "virtual-lab-id": UNRELATED_VIRTUAL_LAB_ID,
    "project-id": UNRELATED_PROJECT_ID,
}


def assert_response(response, expected_status_code=200, context=None):
    assert response.status_code == expected_status_code, (
        f"Request {response.request.method} {response.request.url}: "
        f"expected={expected_status_code}, actual={response.status_code}, "
        f"content={response.content}, context={context}"
    )


def assert_request(client_method, *, expected_status_code=200, context=None, **kwargs):
    response = client_method(**kwargs)
    assert_response(response, expected_status_code=expected_status_code, context=context)
    return response


def stage_circuit_without_edges(source_dir: Path, dest_dir: Path) -> Path:
    """Copy a circuit's config, node sets and nodes files, but none of its edge files.

    Mirrors how campaign generation stages full circuits. Returns the copied config path.
    """
    dest_dir.mkdir(parents=True)
    shutil.copy(source_dir / "circuit_config.json", dest_dir)
    shutil.copy(source_dir / "node_sets.json", dest_dir)
    for nodes_file in source_dir.glob("*/nodes.h5"):
        (dest_dir / nodes_file.parent.name).mkdir()
        shutil.copy(nodes_file, dest_dir / nodes_file.parent.name)
    return dest_dir / "circuit_config.json"
