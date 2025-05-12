from uuid import UUID

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.application import app
from app.dependencies import auth
from app.schemas.auth import UserContext

from tests.utils import (
    AUTH_HEADER_ADMIN,
    AUTH_HEADER_USER_1,
    AUTH_HEADER_USER_2,
    PROJECT_HEADERS,
    PROJECT_ID,
    TOKEN_ADMIN,
    TOKEN_USER_1,
    TOKEN_USER_2,
    UNRELATED_PROJECT_HEADERS,
    UNRELATED_PROJECT_ID,
    UNRELATED_VIRTUAL_LAB_ID,
    VIRTUAL_LAB_ID,
    ClientProxy,
)


@pytest.fixture
def user_context_admin():
    """Admin authenticated user."""
    return UserContext(
        subject=UUID(int=1),
        email=None,
        expiration=None,
        is_authorized=True,
        is_service_admin=True,
        virtual_lab_id=None,
        project_id=None,
        token=HTTPAuthorizationCredentials(scheme="Bearer", credentials=TOKEN_ADMIN),
    )


@pytest.fixture
def user_context_user_1():
    """Admin authenticated user."""
    return UserContext(
        subject=UUID(int=1),
        email=None,
        expiration=None,
        is_authorized=True,
        is_service_admin=False,
        virtual_lab_id=VIRTUAL_LAB_ID,
        project_id=PROJECT_ID,
        token=HTTPAuthorizationCredentials(scheme="Bearer", credentials=TOKEN_USER_1),
    )


@pytest.fixture
def user_context_user_2():
    """Regular authenticated user with different project-id."""
    return UserContext(
        subject=UUID(int=2),
        email=None,
        expiration=None,
        is_authorized=True,
        is_service_admin=False,
        virtual_lab_id=UNRELATED_VIRTUAL_LAB_ID,
        project_id=UNRELATED_PROJECT_ID,
        token=HTTPAuthorizationCredentials(scheme="Bearer", credentials=TOKEN_USER_2),
    )


@pytest.fixture
def user_context_no_project():
    """Regular authenticated user without project-id."""
    return UserContext(
        subject=UUID(int=3),
        email=None,
        expiration=None,
        is_authorized=True,
        is_service_admin=False,
        virtual_lab_id=None,
        project_id=None,
        token=HTTPAuthorizationCredentials(scheme="Bearer", credentials=TOKEN_USER_1),
    )


@pytest.fixture
def _override_check_user_info(
    monkeypatch,
    user_context_admin,
    user_context_user_1,
    user_context_user_2,
    user_context_no_project,
):
    # map (token, project-id) to the expected user_context
    mapping = {
        (TOKEN_ADMIN, None): user_context_admin,
        (TOKEN_USER_1, None): user_context_no_project,
        (TOKEN_USER_1, UUID(PROJECT_ID)): user_context_user_1,
        (TOKEN_USER_2, UUID(UNRELATED_PROJECT_ID)): user_context_user_2,
    }

    def mock_check_user_info(*, project_context, token, http_client):  # noqa: ARG001
        return mapping[token.credentials, project_context.project_id]

    monkeypatch.setattr(auth, "_check_user_info", mock_check_user_info)


@pytest.fixture(scope="session")
def session_client():
    """Run the lifespan events and return a web client instance, not authenticated.

    The fixture is session-scoped so that the lifespan events are executed only once per session.
    """
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_no_auth(session_client, _override_check_user_info):
    """Return a web client instance, not authenticated."""
    return session_client


@pytest.fixture
def client_admin(client_no_auth):
    """Return a web client instance, authenticated as service admin without a project-id."""
    return ClientProxy(client_no_auth, headers=AUTH_HEADER_ADMIN)


@pytest.fixture
def client_user_1(client_no_auth):
    """Return a web client instance, authenticated as regular user with a specific project-id."""
    return ClientProxy(client_no_auth, headers=AUTH_HEADER_USER_1 | PROJECT_HEADERS)


def client_user_2(client_no_auth):
    """Return a web client instance, authenticated as regular user with different project-id."""
    return ClientProxy(client_no_auth, headers=AUTH_HEADER_USER_2 | UNRELATED_PROJECT_HEADERS)


@pytest.fixture
def client_no_project(client_no_auth):
    """Return a web client instance, authenticated as regular user without a project-id."""
    return ClientProxy(client_no_auth, headers=AUTH_HEADER_USER_1)


@pytest.fixture
def client(client_user_1):
    """Alias for client_user_1."""
    return client_user_1
