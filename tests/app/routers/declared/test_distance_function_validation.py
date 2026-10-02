"""Integration tests for the distance-function validation endpoint."""

from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.endpoints.distance_function_validation import router as distance_function_router

ROUTE = "/declared/distance-function/validate"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(distance_function_router)
    app.dependency_overrides[user_verified] = lambda: True
    return TestClient(app)


def test_validate_returns_valid_for_a_safe_function(client):
    response = client.post(ROUTE, json={"function": "math.exp({distance}) * {value}"})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["valid"] is True
    assert body["error"] is None
    # Response uses the `from` alias, not `from_`.
    assert body["from"] == 0
    assert body["to"] == 0


def test_validate_reports_error_span_for_an_unsafe_function(client):
    fn = "os.system('x') + {value} + {distance}"
    response = client.post(ROUTE, json={"function": fn})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["valid"] is False
    assert "calls are limited" in body["error"]
    # The reported span points at the offending call in the original string.
    assert fn[body["from"] : body["to"]] == "os.system('x')"


def test_validate_accepts_declared_parameters(client):
    response = client.post(
        ROUTE,
        json={"function": "math.exp({distance}*{c})*{value}", "parameters": ["c"]},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["valid"] is True


def test_validate_rejects_function_exceeding_max_length(client):
    response = client.post(ROUTE, json={"function": "x" * 600})
    # The request-model `max_length` rejects it before the handler runs.
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
