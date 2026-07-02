"""Additional accounting tests for mesh_lod_generation task type.

The parametrised test below extends the existing test_evaluate_accounting_parameters
to cover the new mesh_lod_generation case.
"""

from unittest.mock import patch
from uuid import uuid4

import entitysdk
import pytest
from obp_accounting_sdk.constants import ServiceSubtype

from app.mappings import TASK_DEFINITIONS
from app.services import accounting as test_module
from app.types import TaskType


@pytest.fixture
def db_client():
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # noqa: S106


def test_evaluate_accounting_parameters_mesh_lod_generation(db_client):
    config_id = uuid4()
    task_definition = TASK_DEFINITIONS[TaskType.mesh_lod_generation]

    res = test_module._evaluate_accounting_parameters(
        db_client=db_client,
        config_id=config_id,
        task_definition=task_definition,
    )

    assert res.service_subtype == ServiceSubtype.NEURON_MESH_SKELETONIZATION
    assert res.count == 1


def test_evaluate_accounting_parameters_mesh_lod_generation_in_parametrized(db_client):
    """Verify mesh_lod_generation is covered by the full parametrized matrix."""
    task_type = TaskType.mesh_lod_generation
    config_id = uuid4()
    task_definition = TASK_DEFINITIONS[task_type]

    with (
        patch(
            "app.services.accounting._evaluate_circuit_simulation_parameters",
            autospec=True,
        ),
        patch("app.services.accounting.estimate_skeletonization_count", return_value=800),
        patch("app.services.accounting.estimate_circuit_extraction_count", return_value=1),
    ):
        res = test_module._evaluate_accounting_parameters(
            db_client=db_client,
            config_id=config_id,
            task_definition=task_definition,
        )

    assert res.service_subtype == ServiceSubtype.NEURON_MESH_SKELETONIZATION
    assert res.count == 1
