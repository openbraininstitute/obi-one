"""Tests for circuit launch-job submission and lifecycle helpers."""

from unittest.mock import MagicMock
from uuid import uuid4

from entitysdk.types import EntityLifecycleStatus

from obi_one.db_sdk.registration.circuit.launch_jobs import (
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
                app_version="1.2.3-dev",
                force=True,
            )
            == job_id
        )

        job = ls_client.post.call_args[1]["json"]
        assert job["code"]["ref"] == "tag:1.2.3"
        assert job["resources"]["image_type"] == "python_3_12_openmpi5_neuron9_neurodamus"
        assert job["resources"]["compute_cell"] == "cell_a"
        assert f"--circuit_id {circuit_id}" in job["inputs"]
        assert "--force true" in job["inputs"]
        assert job["callbacks"][0]["config"]["url"] == (
            f"http://localhost:8100/declared/circuit/{circuit_id}/generate-assets"
        )

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
                project_id=project_id,
                virtual_lab_id=virtual_lab_id,
                compute_cell="cell_b",
                obi_one_repo="https://github.com/org/repo.git",
                app_version="9.9.9",
                force=False,
            )
            == job_id
        )

        job = ls_client.post.call_args[1]["json"]
        assert job["code"]["ref"] == "tag:9.9.9"
        assert "launch_circuit_asset_generation" in job["code"]["path"]
        assert job["resources"]["compute_cell"] == "cell_b"
        assert f"--circuit_id {circuit_id}" in job["inputs"]
        assert "--force false" in job["inputs"]
        assert job["callbacks"] == []
        assert "image_type" not in job["resources"]
