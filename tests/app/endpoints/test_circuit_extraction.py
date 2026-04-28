from unittest.mock import patch
from uuid import uuid4

from obp_accounting_sdk.constants import ServiceSubtype

from app.schemas.accounting import AccountingParameters
from app.schemas.task import TaskAccountingInfo
from app.types import TaskType


def test_circuit_extraction_estimate_endpoint(client):
    config_id = uuid4()
    expected = TaskAccountingInfo(
        task_type=TaskType.circuit_extraction,
        config_id=config_id,
        cost=12.5,
        parameters=AccountingParameters(
            count=42,
            service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION,
        ),
    )

    with patch("app.services.accounting.estimate_task_cost", return_value=expected, autospec=True):
        response = client.post(
            "/declared/circuit-extraction/estimate",
            params={"config_id": str(config_id)},
        )

    response.raise_for_status()
    payload = response.json()
    assert payload["task_type"] == "circuit_extraction"
    assert payload["config_id"] == str(config_id)
    assert payload["cost"] == 12.5
    assert payload["parameters"]["count"] == 42
    assert payload["parameters"]["service_subtype"] == "circuit-extraction"
