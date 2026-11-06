"""Tests for register_circuit_with_remote_validation."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from entitysdk.types import CircuitBuildCategory, TargetSimulator

from obi_one.db_sdk.registration.circuit.remote import register_circuit_with_remote_validation

REGISTER = "obi_one.db_sdk.registration.circuit.remote.register_circuit"


def _call(obi_one_client, client=None):
    return register_circuit_with_remote_validation(
        client or MagicMock(),
        "/some/circuit.tar.gz",
        obi_one_client=obi_one_client,
        name="c",
        description="d",
        build_category=CircuitBuildCategory.computational_model,
        brain_region=MagicMock(),
        subject=MagicMock(),
        target_simulator=TargetSimulator.NEURON,
    )


class TestRegisterCircuitWithRemoteValidation:
    def test_dry_run_skips_validation_request(self):
        preview = MagicMock()
        obi_one_client = MagicMock()

        with patch(REGISTER, return_value=preview) as mock_register:
            circuit, job_id = register_circuit_with_remote_validation(
                MagicMock(),
                "/some/circuit",
                obi_one_client=obi_one_client,
                name="c",
                description="d",
                build_category=CircuitBuildCategory.computational_model,
                brain_region=MagicMock(),
                subject=MagicMock(),
                target_simulator=TargetSimulator.NEURON,
                dry_run=True,
            )

        assert mock_register.call_args.kwargs["dry_run"] is True
        assert circuit is preview
        assert job_id is None
        obi_one_client.post.assert_not_called()

    def test_registers_draft_then_triggers_validation(self):
        registered = MagicMock()
        registered.id = uuid4()
        job_id = uuid4()
        obi_one_client = MagicMock()
        obi_one_client.post.return_value.json.return_value = {"job_id": str(job_id)}
        client = MagicMock()

        with patch(REGISTER, return_value=registered) as mock_register:
            circuit, returned_job_id = _call(obi_one_client, client)

        kwargs = mock_register.call_args.kwargs
        assert kwargs["lifecycle_status"] == "draft"
        assert kwargs["skip_validation"] is True
        assert kwargs["skip_additional_assets"] is True
        assert circuit is registered
        assert returned_job_id == job_id

        args, post_kwargs = obi_one_client.post.call_args
        assert args == (f"/declared/circuit/{registered.id}/validate",)
        assert post_kwargs["params"] == {"generate_assets": "true"}
        assert post_kwargs["headers"] == {
            "virtual-lab-id": str(client.project_context.virtual_lab_id),
            "project-id": str(client.project_context.project_id),
        }

    def test_validation_failure_mentions_draft_circuit(self):
        registered = MagicMock()
        registered.id = uuid4()
        obi_one_client = MagicMock()
        obi_one_client.post.return_value.raise_for_status.side_effect = httpx.HTTPError("boom")

        with patch(REGISTER, return_value=registered), pytest.raises(RuntimeError) as exc_info:
            _call(obi_one_client)

        assert str(registered.id) in str(exc_info.value)
        assert "draft" in str(exc_info.value)
