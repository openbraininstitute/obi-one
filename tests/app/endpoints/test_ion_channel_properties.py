"""Tests for the ion channel properties endpoints, including the Task 2 variable catalog."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.application import app
from app.dependencies.entitysdk import get_client

from tests.utils import AUTH_HEADER_USER_1, PROJECT_HEADERS

VARIABLE_CATALOG_ENDPOINT = "/declared/mapped-ion-channel-properties/emodel-optimization-variables"


def _fake_entity():
    return SimpleNamespace(
        id="icm-1",
        name="Sodium channel",
        nmodl_suffix="NaTg",
        is_stochastic=False,
        is_ljp_corrected=False,
        temperature_celsius=34,
        neuron_block=SimpleNamespace(
            range=[{"gNa": "S/cm2"}],
            global_=[{"ena": "mV"}],
        ),
    )


@pytest.fixture
def _mock_client():
    mock = MagicMock()
    mock.get_entity.return_value = _fake_entity()
    app.dependency_overrides[get_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_client, None)


@pytest.fixture
def client(_override_check_user_info, _mock_client):
    """Test client with mocked db_client dependency."""
    with TestClient(app) as test_client:
        yield test_client


class TestEModelOptimizationVariableCatalogEndpoint:
    """Tests for GET .../emodel-optimization-variables."""

    def test_returns_qualified_range_and_global_variables(self, client):
        response = client.get(
            VARIABLE_CATALOG_ENDPOINT,
            params={"ion_channel_ids": ["icm-1"]},
            headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
        )

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"icm-1"}

        entry = data["icm-1"]
        assert entry["nmodl_suffix"] == "NaTg"
        variables_by_name = {variable["name"]: variable for variable in entry["variables"]}

        assert variables_by_name["gNa_NaTg"]["source_name"] == "gNa"
        assert variables_by_name["gNa_NaTg"]["units"] == "S/cm2"
        assert variables_by_name["gNa_NaTg"]["variable_type"] == "RANGE"
        assert variables_by_name["gNa_NaTg"]["allowed_group"] == "region"

        assert variables_by_name["ena_NaTg"]["variable_type"] == "GLOBAL"
        assert variables_by_name["ena_NaTg"]["allowed_group"] == "global"
