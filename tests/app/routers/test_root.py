from app.config import settings


def test_root(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_VERSION", "0000.0.0")

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Welcome to obi-one 0000.0.0. See /docs for OpenAPI documentation."
    }


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_version(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_VERSION", "0000.0.0")
    monkeypatch.setattr(settings, "COMMIT_SHA", "0000000")

    response = client.get("/version")

    assert response.status_code == 200
    response_json = response.json()
    assert response_json == {
        "app_name": "obi-one",
        "app_version": "0000.0.0",
        "commit_sha": "0000000",
    }
