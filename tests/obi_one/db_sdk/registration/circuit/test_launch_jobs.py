"""Tests for circuit launch-job submission and lifecycle helpers."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.types import CircuitScale, EntityLifecycleStatus

from app.services.resource_estimation.circuit_extraction import CPU_MEMORY_COMBINATIONS
from obi_one.db_sdk.registration.circuit.launch_jobs import (
    ASSET_GENERATION_RESOURCES,
    submit_circuit_asset_generation_job,
    submit_circuit_validation_job,
)
from obi_one.db_sdk.registration.circuit.lifecycle import (
    is_validation_allowed,
    validation_blocked_detail,
)


class TestIsValidationAllowed:
    def test_force_allows_any_status(self):
        assert is_validation_allowed(lifecycle_status="active", force=True) is True
        assert is_validation_allowed(lifecycle_status="disqualified", force=True) is True

    def test_none_status_allowed(self):
        assert is_validation_allowed(lifecycle_status=None, force=False) is True

    def test_draft_string_and_enum_allowed(self):
        assert is_validation_allowed(lifecycle_status="draft", force=False) is True
        assert (
            is_validation_allowed(lifecycle_status=EntityLifecycleStatus.draft, force=False) is True
        )

    def test_non_draft_blocked(self):
        assert is_validation_allowed(lifecycle_status="active", force=False) is False
        assert is_validation_allowed(lifecycle_status="disqualified", force=False) is False

    def test_blocked_detail_mentions_force(self):
        detail = validation_blocked_detail("active")
        assert "active" in detail
        assert "force=true" in detail


class TestSubmitCircuitJobs:
    def test_validation_job_payload(self):
        ls_client = MagicMock()
        job_id = uuid4()
        ls_client.post.return_value = MagicMock(
            is_success=True,
            json=MagicMock(return_value={"id": str(job_id)}),
        )
        circuit_id = uuid4()
        project_id = uuid4()
        virtual_lab_id = uuid4()

        assert (
            submit_circuit_validation_job(
                ls_client=ls_client,
                circuit_id=circuit_id,
                project_id=project_id,
                virtual_lab_id=virtual_lab_id,
                api_url="http://localhost:8100",
                compute_cell="cell_a",
                obi_one_repo="https://github.com/org/repo.git",
                app_version="2026.8.12",
                force=True,
            )
            == job_id
        )

        job = ls_client.post.call_args[1]["json"]
        assert job["code"]["ref"] == "tag:2026.8.12"
        assert job["code"]["dependencies"] == (
            "launch_scripts/launch_circuit_validation/dependencies/default.txt"
        )
        assert "dependency_constraints" not in job["code"]
        assert job["resources"]["image_type"] == "python_3_12_openmpi5_neuron9_neurodamus"
        assert job["resources"]["compute_cell"] == "cell_a"
        assert f"--circuit_id {circuit_id}" in job["inputs"]
        assert "--force true" in job["inputs"]
        assert job["callbacks"][0]["config"]["url"] == (
            f"http://localhost:8100/declared/circuit/{circuit_id}/generate-assets"
        )
        # The generate-assets callback must forward the project context so the endpoint can
        # resolve the compute cell and entitysdk client (otherwise it fails with
        # "No virtual lab ID found").
        assert job["callbacks"][0]["config"]["headers"] == {
            "virtual-lab-id": str(virtual_lab_id),
            "project-id": str(project_id),
        }

    def test_validation_job_without_asset_callback(self):
        ls_client = MagicMock()
        job_id = uuid4()
        ls_client.post.return_value = MagicMock(
            is_success=True,
            json=MagicMock(return_value={"id": str(job_id)}),
        )
        circuit_id = uuid4()
        project_id = uuid4()
        virtual_lab_id = uuid4()

        assert (
            submit_circuit_validation_job(
                ls_client=ls_client,
                circuit_id=circuit_id,
                project_id=project_id,
                virtual_lab_id=virtual_lab_id,
                api_url="http://localhost:8100",
                compute_cell="cell_a",
                generate_assets_on_success=False,
            )
            == job_id
        )

        job = ls_client.post.call_args[1]["json"]
        assert job["callbacks"] == []

    def test_validation_job_submission_failure_returns_none(self):
        ls_client = MagicMock()
        ls_client.post.return_value = MagicMock(is_success=False, text="boom")

        assert (
            submit_circuit_validation_job(
                ls_client=ls_client,
                circuit_id=uuid4(),
                project_id=uuid4(),
                virtual_lab_id=uuid4(),
                api_url="http://localhost:8100",
                compute_cell="cell_a",
            )
            is None
        )

    def test_asset_generation_job_payload(self):
        ls_client = MagicMock()
        job_id = uuid4()
        ls_client.post.return_value = MagicMock(
            is_success=True,
            json=MagicMock(return_value={"id": str(job_id)}),
        )
        circuit_id = uuid4()
        project_id = uuid4()
        virtual_lab_id = uuid4()

        assert (
            submit_circuit_asset_generation_job(
                ls_client=ls_client,
                circuit_id=circuit_id,
                scale=None,
                project_id=project_id,
                virtual_lab_id=virtual_lab_id,
                compute_cell="cell_b",
                obi_one_repo="https://github.com/org/repo.git",
                app_version="2026.9.1",
                force=False,
            )
            == job_id
        )

        job = ls_client.post.call_args[1]["json"]
        assert job["code"]["ref"] == "tag:2026.9.1"
        assert job["code"]["dependencies"] == (
            "launch_scripts/launch_circuit_asset_generation/dependencies/default.txt"
        )
        assert "dependency_constraints" not in job["code"]
        assert "launch_circuit_asset_generation" in job["code"]["path"]
        assert job["resources"]["compute_cell"] == "cell_b"
        assert job["resources"]["cores"] == 2
        assert job["resources"]["memory"] == 16
        assert f"--circuit_id {circuit_id}" in job["inputs"]
        assert "--force false" in job["inputs"]
        assert job["callbacks"] == []
        assert "image_type" not in job["resources"]

    @pytest.mark.parametrize(
        ("scale", "cores", "memory"),
        [
            (CircuitScale.pair, 1, 4),
            (CircuitScale.small, 1, 4),
            (CircuitScale.microcircuit, 2, 16),
            (CircuitScale.whole_brain, 4, 16),
            (None, 2, 16),
        ],
    )
    def test_asset_generation_job_resources(self, scale, cores, memory):
        ls_client = MagicMock()
        ls_client.post.return_value = MagicMock(
            is_success=True, json=MagicMock(return_value={"id": str(uuid4())})
        )
        submit_circuit_asset_generation_job(
            ls_client=ls_client,
            circuit_id=uuid4(),
            scale=scale,
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
            compute_cell="cell_a",
        )
        resources = ls_client.post.call_args[1]["json"]["resources"]
        assert (resources["cores"], resources["memory"]) == (cores, memory)

    def test_asset_generation_resources_are_launch_system_combinations(self):
        for cores, memory in ASSET_GENERATION_RESOURCES.values():
            assert memory in CPU_MEMORY_COMBINATIONS[cores]

    @pytest.mark.parametrize(
        ("compute_cell", "placement"),
        [("cell_a", "fargate"), ("cell_b", "azure_container_apps"), ("local", None)],
    )
    def test_asset_generation_job_placement(self, compute_cell, placement):
        ls_client = MagicMock()
        ls_client.post.return_value = MagicMock(
            is_success=True, json=MagicMock(return_value={"id": str(uuid4())})
        )
        submit_circuit_asset_generation_job(
            ls_client=ls_client,
            circuit_id=uuid4(),
            scale=None,
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
            compute_cell=compute_cell,
        )
        assert ls_client.post.call_args[1]["json"]["resources"]["placement_type"] == placement

    @pytest.mark.parametrize(
        ("app_version", "expected_ref"),
        [
            (None, "tag:0.0.0"),
            ("2026.8.12-3-g49a16415-dirty", "tag:2026.8.12"),
            ("2026.8.12-3-g49a16415", "tag:2026.8.12"),
        ],
    )
    def test_dev_version_uses_last_release_tag(self, app_version, expected_ref):
        ls_client = MagicMock()
        ls_client.post.return_value = MagicMock(
            is_success=True,
            json=MagicMock(return_value={"id": str(uuid4())}),
        )

        submit_circuit_asset_generation_job(
            ls_client=ls_client,
            circuit_id=uuid4(),
            scale=None,
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
            compute_cell="cell_b",
            obi_one_repo="https://github.com/org/repo.git",
            app_version=app_version,
            force=False,
        )

        job = ls_client.post.call_args[1]["json"]
        # Post-release / dirty dev builds check out the last release's tag.
        assert job["code"]["ref"] == expected_ref
