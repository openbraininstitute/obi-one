from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import callback as test_module


def test_get_task_callback_url_returns_settings_value(monkeypatch):
    # Arrange
    monkeypatch.setattr(settings, "API_URL", "http://testserver/callback")

    # Act
    result = test_module.get_task_callback_url()

    # Assert
    assert result == "http://testserver/callback"


def test_callback_url_dependency_injection(monkeypatch):
    # Arrange
    monkeypatch.setattr(settings, "API_URL", "http://testserver/callback")

    app = FastAPI()

    @app.get("/test")
    def test_endpoint(callback_url: test_module.CallBackUrlDep):
        return {"callback_url": callback_url}

    client = TestClient(app)

    # Act
    response = client.get("/test")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"callback_url": "http://testserver/callback"}
