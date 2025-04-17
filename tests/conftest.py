import pytest
from fastapi.testclient import TestClient

from app.application import app


@pytest.fixture(scope="session")
def client():
    """Run the lifespan events.

    The fixture is session-scoped so that the lifespan events are executed only once per session.
    """
    with TestClient(app) as client:
        yield client
