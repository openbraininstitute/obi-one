"""Integration tests for circuit registration and customization.

Run against staging with:
    source .env.test-local
    pytest tests/integration/ -v --no-cov -m integration

Requires:
    - obi-one API running locally or on staging
    - Valid env vars (API_URL, ENTITYCORE_URL, LAUNCH_SYSTEM_URL, etc.)
"""

import io
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from uuid import UUID

import h5py
import httpx
import numpy as np
import pytest

TINY_CIRCUIT_ARCHIVE = (
    Path(__file__).parents[2] / "examples" / "data" / "tiny_circuits" / "N_10__top_nodes_dim6.gz"
)

# Valid IDs from staging (from circuit aef2a8b8-985f-43e4-9b95-7c05faf61c9f)
BRAIN_REGION_ID = "dfb8b0d8-1860-4afc-82e1-6e922ef78f20"
SUBJECT_ID = "e5ecb660-504f-4840-b674-f31f0eada439"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api_url():
    """Base URL of the obi-one API."""
    import os
    return os.environ.get("API_URL", "http://127.0.0.1:8100")


@pytest.fixture(scope="module")
def auth_headers():
    """Auth headers for API calls. Token read from file or env var."""
    import os
    token_file = Path(__file__).parents[2] / ".token"
    if token_file.exists():
        token = token_file.read_text().strip()
    else:
        token = os.environ.get("TEST_TOKEN", "")
    if not token:
        pytest.skip("No token: set TEST_TOKEN env var or put token in .token file")
    return {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": os.environ.get("TEST_VIRTUAL_LAB_ID", "ff888f05-f314-4702-8a92-b86f754270bb"),
        "project-id": os.environ.get("TEST_PROJECT_ID", "462ace35-28b4-45e3-8db0-9a7a18093e83"),
    }


@pytest.fixture(scope="module")
def client(api_url, auth_headers):
    with httpx.Client(base_url=api_url, headers=auth_headers, timeout=60) as c:
        yield c


@pytest.fixture(scope="module")
def entitycore_url():
    import os
    return os.environ.get("ENTITYCORE_URL", "https://staging.cell-a.openbraininstitute.org/api/entitycore")


@pytest.fixture(scope="module")
def entitycore_client(entitycore_url, auth_headers):
    with httpx.Client(base_url=entitycore_url, headers=auth_headers, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def registered_circuit(client):
    """Register the tiny circuit as the parent. Shared across all tests in this module."""
    with open(TINY_CIRCUIT_ARCHIVE, "rb") as f:
        response = client.post(
            "/declared/circuit/register",
            data={
                "name": "Integration Test Parent Circuit",
                "description": "Tiny N=10 circuit for integration testing",
                "brain_region_id": BRAIN_REGION_ID,
                "subject_id": SUBJECT_ID,
                "build_category": "computational_model",
                "target_simulator": "NEURON",
            },
            files={"circuit_archive": ("circuit.tar.gz", f, "application/gzip")},
        )
    assert response.status_code == 200, f"Registration failed: {response.text}"
    return response.json()


def _wait_for_status(entitycore_client, circuit_id, target_statuses, timeout=120):
    """Poll EntityCore lifecycle_status until it reaches one of the target statuses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = entitycore_client.get(f"/circuit/{circuit_id}")
        if resp.status_code == 200:
            status = resp.json().get("lifecycle_status")
            if status in target_statuses:
                return status
        time.sleep(5)
    pytest.fail(f"Circuit {circuit_id} did not reach {target_statuses} within {timeout}s")


# ---------------------------------------------------------------------------
# Test 1: Registration happy path
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_returns_draft(self, registered_circuit):
        assert registered_circuit["status"] == "draft"
        assert int(registered_circuit["number_neurons"]) == 10

    def test_validation_completes(self, entitycore_client, registered_circuit):
        """After registration, validation task should transition to active."""
        circuit_id = registered_circuit["circuit_id"]
        status = _wait_for_status(entitycore_client, circuit_id, {"active", "failed"})
        assert status == "active"


# ---------------------------------------------------------------------------
# Test 2: Alzheimer disease model customization (bundle)
# ---------------------------------------------------------------------------


class TestAlzheimerCustomization:
    """Bundle customization: modified HOC + modified edges + new edges + updated nodes."""

    def _make_modified_hoc(self, tmp_path: Path) -> Path:
        """Modify cADpyr_L6BPC.hoc — reduce NaTg gbar (Aβ effect on Nav1.6)."""
        with tarfile.open(TINY_CIRCUIT_ARCHIVE) as t:
            f = t.extractfile("circuit/emodels_hoc/cADpyr_L6BPC.hoc")
            content = f.read().decode()

        # Simulate Alzheimer modification: scale down NaTg conductance
        modified = content.replace(
            "gNaTgbar_NaTg",
            "gNaTgbar_NaTg  // AD-modified: reduced Nav1.6\n    // gNaTgbar_NaTg",
        )
        # Keep valid structure — just add a comment marking it as modified
        if modified == content:
            # Fallback: just add a comment at the top
            modified = "// Alzheimer disease model: reduced Nav1.6 conductance\n" + content

        out = tmp_path / "cADpyr_L6BPC.hoc"
        out.write_text(modified)
        return out

    def _make_modified_edges(self, tmp_path: Path) -> Path:
        """Modify S1 edges — reduce conductance_scale_factor (synaptic loss)."""
        with tarfile.open(TINY_CIRCUIT_ARCHIVE) as t:
            f = t.extractfile(
                "circuit/S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/edges.h5"
            )
            raw = f.read()

        edges_path = tmp_path / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical_edges.h5"
        with h5py.File(io.BytesIO(raw), "r") as src, h5py.File(edges_path, "w") as dst:
            # Copy everything
            for key in src:
                src.copy(key, dst)
            # Modify conductance_scale_factor (reduce by 30% — Aβ synaptic loss)
            pop_name = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical"
            csf = dst[f"edges/{pop_name}/0/conductance_scale_factor"]
            csf[:] = csf[:] * 0.7

        return edges_path

    def _make_new_edges(self, tmp_path: Path) -> Path:
        """Create a small new edge population (compensatory inhibitory connections)."""
        new_edges_path = tmp_path / "AD_compensatory_inhibition_edges.h5"
        pop_name = "AD_compensatory_inhibition"
        n_edges = 5

        with h5py.File(new_edges_path, "w") as f:
            pop = f.create_group(f"edges/{pop_name}")
            pop.create_dataset("source_node_id", data=np.array([0, 1, 2, 3, 4], dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.array([5, 6, 7, 8, 9], dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n_edges, dtype=np.int32))

            grp = pop.create_group("0")
            grp.create_dataset("conductance", data=np.full(n_edges, 0.5, dtype=np.float32))
            grp.create_dataset("delay", data=np.full(n_edges, 1.5, dtype=np.float32))
            grp.create_dataset(
                "conductance_scale_factor", data=np.ones(n_edges, dtype=np.float32)
            )

        return new_edges_path

    def _make_updated_nodes(self, tmp_path: Path) -> Path:
        """Copy nodes file unchanged (model_template still references cADpyr_L6BPC)."""
        with tarfile.open(TINY_CIRCUIT_ARCHIVE) as t:
            f = t.extractfile("circuit/S1nonbarrel_neurons/nodes.h5")
            raw = f.read()

        nodes_path = tmp_path / "S1nonbarrel_neurons_nodes.h5"
        nodes_path.write_bytes(raw)
        return nodes_path

    def test_alzheimer_customization(self, client, entitycore_client, registered_circuit, tmp_path):
        """Full Alzheimer bundle: modified HOC + modified edges + nodes."""
        parent_id = registered_circuit["circuit_id"]

        hoc_path = self._make_modified_hoc(tmp_path)
        modified_edges = self._make_modified_edges(tmp_path)
        nodes_path = self._make_updated_nodes(tmp_path)

        files = [
            ("emodel_files", (hoc_path.name, open(hoc_path, "rb"), "application/octet-stream")),
            ("edges_files", (modified_edges.name, open(modified_edges, "rb"), "application/octet-stream")),
            ("node_files", (nodes_path.name, open(nodes_path, "rb"), "application/octet-stream")),
        ]

        response = client.post(
            "/declared/circuit/customize",
            data={
                "parent_circuit_id": parent_id,
                "name": "Alzheimer Disease Model",
                "description": "Aβ effects: reduced Nav1.6, synaptic loss, compensatory inhibition",
            },
            files=files,
        )
        assert response.status_code == 200, f"Customization failed: {response.text}"
        data = response.json()
        assert data["status"] == "draft"

        # Wait for async validation
        status = _wait_for_status(entitycore_client, data["circuit_id"], {"active", "failed"})
        assert status == "active"


# ---------------------------------------------------------------------------
# Test 3: Rejection — bad HOC (sync)
# ---------------------------------------------------------------------------


class TestSyncRejections:
    def test_bad_hoc_rejected(self, client, registered_circuit, tmp_path):
        """HOC file missing endtemplate should be rejected at upload."""
        parent_id = registered_circuit["circuit_id"]

        bad_hoc = tmp_path / "broken.hoc"
        bad_hoc.write_text("begintemplate BrokenCell\nproc init() {}\n// missing endtemplate\n")

        response = client.post(
            "/declared/circuit/customize",
            data={
                "parent_circuit_id": parent_id,
                "name": "Bad HOC test",
                "description": "Should fail",
            },
            files=[("emodel_files", ("broken.hoc", open(bad_hoc, "rb"), "application/octet-stream"))],
        )
        assert response.status_code == 422

    def test_new_synapse_mod_rejected(self, client, registered_circuit, tmp_path):
        """New MOD file with NET_RECEIVE should be rejected."""
        parent_id = registered_circuit["circuit_id"]

        synapse_mod = tmp_path / "NewSynapse.mod"
        synapse_mod.write_text(
            "NEURON {\n  POINT_PROCESS NewSynapse\n}\n"
            "NET_RECEIVE (weight) {\n  state = state + weight\n}\n"
        )

        response = client.post(
            "/declared/circuit/customize",
            data={
                "parent_circuit_id": parent_id,
                "name": "Synapse MOD test",
                "description": "Should fail",
            },
            files=[("mechanism_files", ("NewSynapse.mod", open(synapse_mod, "rb"), "application/octet-stream"))],
        )
        # Should get validation error (either 422 or 200 with errors in body)
        if response.status_code == 200:
            assert "error" in response.text.lower() or "NET_RECEIVE" in response.text
        else:
            assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test 4: Async failure — HOC uses mechanism not in circuit
# ---------------------------------------------------------------------------


class TestAsyncFailure:
    @pytest.mark.xfail(reason="circuit_validation task not yet deployed to staging ECS")
    def test_mod_compilation_fails(self, client, entitycore_client, registered_circuit, tmp_path):
        """MOD file with valid structure but broken NMODL passes Layer 1, fails async compile."""
        parent_id = registered_circuit["circuit_id"]

        # MOD that has NEURON block (passes Layer 1) but has syntax errors in PROCEDURE
        broken_mod = tmp_path / "BrokenMech.mod"
        broken_mod.write_text(
            "NEURON {\n  SUFFIX BrokenMech\n  RANGE x\n}\n"
            "PARAMETER {\n  x = 0\n}\n"
            "PROCEDURE rates() {\n"
            "  THIS_IS_NOT_VALID_NMODL syntax error here\n"
            "}\n"
        )

        # HOC that uses this broken mechanism (take existing and add insert)
        hoc_path = tmp_path / "cADpyr_L6BPC.hoc"
        with tarfile.open(TINY_CIRCUIT_ARCHIVE) as t:
            f = t.extractfile("circuit/emodels_hoc/cADpyr_L6BPC.hoc")
            content = f.read().decode()
        content = content.replace("insert NaTg", "insert NaTg\n    insert BrokenMech")
        hoc_path.write_text(content)

        response = client.post(
            "/declared/circuit/customize",
            data={
                "parent_circuit_id": parent_id,
                "name": "Broken MOD test",
                "description": "Should pass sync, fail async (nrnivmodl compilation failure)",
            },
            files=[
                ("emodel_files", (hoc_path.name, open(hoc_path, "rb"), "application/octet-stream")),
                ("mechanism_files", (broken_mod.name, open(broken_mod, "rb"), "application/octet-stream")),
            ],
        )
        assert response.status_code == 200, f"Unexpected sync failure: {response.text}"
        data = response.json()
        assert data["status"] == "draft"

        # Async validation should fail (nrnivmodl won't compile the broken MOD)
        status = _wait_for_status(entitycore_client, data["circuit_id"], {"active", "failed"})
        assert status == "failed"
