import time
import uuid
from unittest.mock import Mock

import httpx
import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.dependencies import auth as test_module
from app.errors import ApiError, ApiErrorCode, AuthErrorReason
from app.schemas.auth import UserContext, UserContextWithProjectId
from app.schemas.base import OptionalProjectContext

from tests.utils import PROJECT_ID, UNRELATED_PROJECT_ID, UNRELATED_VIRTUAL_LAB_ID, VIRTUAL_LAB_ID

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
TEST_USER_SUB = "4e234816-1391-4704-ab96-93f2c0875b42"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_NAME = "John Doe"

PROJECT_CONTEXTS = [
    OptionalProjectContext(virtual_lab_id=None, project_id=None),
    OptionalProjectContext(virtual_lab_id=VIRTUAL_LAB_ID, project_id=PROJECT_ID),
]


@pytest.fixture(autouse=True)
def _clear_cache():
    yield
    test_module._check_user_info.cache_clear()


@pytest.fixture
def http_client():
    with httpx.Client() as client:
        yield client


@pytest.fixture
def request_mock(http_client):
    request = Mock()
    request.state.http_client = http_client
    return request


def _get_token(exp):
    decoded = {"sub": TEST_USER_SUB, "exp": exp, "email": TEST_USER_EMAIL}
    encoded = jwt.encode(decoded, "secret", algorithm="HS256")
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=encoded)


@pytest.mark.parametrize("project_context", PROJECT_CONTEXTS)
@pytest.mark.parametrize("is_token_jwt", [True, False])
@pytest.mark.parametrize("is_admin", [True, False])
@pytest.mark.usefixtures("freezer")
def test_user_verified_ok(httpx_mock, request_mock, is_admin, is_token_jwt, project_context):
    if is_token_jwt:
        token_expiration = int(time.time() + 3600)
        token = _get_token(exp=token_expiration)
    else:
        token_expiration = None
        token = HTTPAuthorizationCredentials(scheme="Bearer", credentials="random-ascii-token")

    httpx_mock.add_response(
        method="GET",
        url=test_module.KEYCLOAK_GROUPS_URL,
        match_headers={"Authorization": f"{token.scheme} {token.credentials}"},
        json={
            "sub": TEST_USER_SUB,
            "name": TEST_USER_NAME,
            "email": TEST_USER_EMAIL,
            "groups": [
                f"/service/{settings.APP_NAME}/admin" if is_admin else "/other",
                f"/proj/{VIRTUAL_LAB_ID}/{PROJECT_ID}/admin",
                f"/vlab/{VIRTUAL_LAB_ID}/admin",
            ],
        },
    )

    result = test_module.user_verified(
        project_context=project_context, token=token, request=request_mock
    )
    assert isinstance(result, UserContext)
    assert result == UserContext(
        subject=uuid.UUID(TEST_USER_SUB),
        email=TEST_USER_EMAIL,
        expiration=token_expiration,
        is_authorized=True,
        is_service_admin=is_admin,
        virtual_lab_id=project_context.virtual_lab_id,
        project_id=project_context.project_id,
        token=token,
    )


@pytest.mark.parametrize("project_context", PROJECT_CONTEXTS)
def test_user_verified_ok_when_auth_is_disabled(monkeypatch, request_mock, project_context):
    monkeypatch.setattr(settings, "APP_DISABLE_AUTH", True)
    result = test_module.user_verified(
        project_context=project_context, token=None, request=request_mock
    )
    assert isinstance(result, UserContext)
    assert result == UserContext(
        subject=uuid.UUID(ZERO_UUID),
        email=None,
        expiration=None,
        is_authorized=True,
        is_service_admin=True,
        virtual_lab_id=project_context.virtual_lab_id,
        project_id=project_context.project_id,
        token=None,
    )


def test_user_verified_without_token(request_mock):
    project_context = OptionalProjectContext(virtual_lab_id=None, project_id=None)
    with pytest.raises(ApiError) as excinfo:
        test_module.user_verified(project_context=project_context, token=None, request=request_mock)
    assert excinfo.value == ApiError(
        message=AuthErrorReason.AUTH_TOKEN_MISSING,
        error_code=ApiErrorCode.NOT_AUTHENTICATED,
        http_status_code=401,
    )


def test_user_verified_with_token_non_ascii(request_mock):
    project_context = OptionalProjectContext(virtual_lab_id=None, project_id=None)
    token = HTTPAuthorizationCredentials(scheme="Bearer", credentials="non-ascii-credential-é")
    with pytest.raises(ApiError) as excinfo:
        test_module.user_verified(
            project_context=project_context, token=token, request=request_mock
        )
    assert excinfo.value == ApiError(
        message=AuthErrorReason.AUTH_TOKEN_INVALID,
        error_code=ApiErrorCode.NOT_AUTHENTICATED,
        http_status_code=401,
    )


@pytest.mark.parametrize("project_context", PROJECT_CONTEXTS)
@pytest.mark.usefixtures("freezer")
def test_user_verified_with_expired_token(request_mock, project_context):
    token_expiration = int(time.time() - 1)
    token = _get_token(exp=token_expiration)

    with pytest.raises(ApiError) as excinfo:
        test_module.user_verified(
            project_context=project_context, token=token, request=request_mock
        )
    assert excinfo.value == ApiError(
        message=AuthErrorReason.AUTH_TOKEN_EXPIRED,
        error_code=ApiErrorCode.NOT_AUTHENTICATED,
        http_status_code=401,
    )


@pytest.mark.parametrize("project_context", PROJECT_CONTEXTS)
@pytest.mark.parametrize(
    ("keycloak_status", "expected_error"),
    [
        (
            401,
            ApiError(
                message=AuthErrorReason.NOT_AUTHENTICATED_USER,
                error_code=ApiErrorCode.NOT_AUTHENTICATED,
                http_status_code=401,
            ),
        ),
        (
            403,
            ApiError(
                message=AuthErrorReason.NOT_AUTHORIZED_USER,
                error_code=ApiErrorCode.NOT_AUTHORIZED,
                http_status_code=403,
            ),
        ),
        (
            500,
            ApiError(
                message="HTTP status error 500",
                error_code=ApiErrorCode.GENERIC_ERROR,
                http_status_code=500,
            ),
        ),
    ],
)
@pytest.mark.usefixtures("freezer")
def test_user_verified_keycloak_error(
    httpx_mock, request_mock, keycloak_status, expected_error, project_context
):
    token_expiration = int(time.time() + 3600)
    token = _get_token(exp=token_expiration)

    httpx_mock.add_response(
        status_code=keycloak_status,
        method="GET",
        url=test_module.KEYCLOAK_GROUPS_URL,
        match_headers={"Authorization": f"{token.scheme} {token.credentials}"},
    )

    with pytest.raises(ApiError) as excinfo:
        test_module.user_verified(
            project_context=project_context, token=token, request=request_mock
        )
    assert excinfo.value == expected_error


@pytest.mark.parametrize(
    # ("project_context", "expected_error"),
    "project_context",
    [
        OptionalProjectContext(virtual_lab_id=VIRTUAL_LAB_ID, project_id=PROJECT_ID),
        OptionalProjectContext(virtual_lab_id=None, project_id=PROJECT_ID),
        OptionalProjectContext(virtual_lab_id=VIRTUAL_LAB_ID, project_id=None),
    ],
)
@pytest.mark.usefixtures("freezer")
def test_user_verified_not_authorized_for_project(httpx_mock, request_mock, project_context):
    token_expiration = int(time.time() + 3600)
    token = _get_token(exp=token_expiration)

    httpx_mock.add_response(
        status_code=200,
        method="GET",
        url=test_module.KEYCLOAK_GROUPS_URL,
        match_headers={"Authorization": f"{token.scheme} {token.credentials}"},
        json={
            "sub": TEST_USER_SUB,
            "name": TEST_USER_NAME,
            "email": TEST_USER_EMAIL,
            "groups": [
                f"/service/{settings.APP_NAME}/admin",
                f"/proj/{UNRELATED_VIRTUAL_LAB_ID}/{UNRELATED_PROJECT_ID}/admin",
                f"/vlab/{UNRELATED_VIRTUAL_LAB_ID}/admin",
            ],
        },
    )

    with pytest.raises(ApiError) as excinfo:
        test_module.user_verified(
            project_context=project_context, token=token, request=request_mock
        )
    assert excinfo.value == ApiError(
        message=AuthErrorReason.NOT_AUTHORIZED_PROJECT,
        error_code=ApiErrorCode.NOT_AUTHORIZED,
        http_status_code=403,
    )


def test_user_with_project_id_ok():
    user_context = UserContext(
        subject=uuid.UUID(TEST_USER_SUB),
        email=TEST_USER_EMAIL,
        expiration=None,
        is_authorized=True,
        is_service_admin=True,
        virtual_lab_id=VIRTUAL_LAB_ID,
        project_id=PROJECT_ID,
        token=None,
    )

    result = test_module.user_with_project_id(user_context)
    assert isinstance(result, UserContextWithProjectId)
    assert result.virtual_lab_id == uuid.UUID(VIRTUAL_LAB_ID)
    assert result.project_id == uuid.UUID(PROJECT_ID)


@pytest.mark.parametrize(
    "project_context",
    [
        OptionalProjectContext(virtual_lab_id=None, project_id=None),
        OptionalProjectContext(virtual_lab_id=VIRTUAL_LAB_ID, project_id=None),
        OptionalProjectContext(virtual_lab_id=None, project_id=PROJECT_ID),
    ],
)
def test_user_with_project_id_raises(project_context):
    user_context = UserContext(
        subject=uuid.UUID(TEST_USER_SUB),
        email=TEST_USER_EMAIL,
        expiration=None,
        is_authorized=True,
        is_service_admin=True,
        virtual_lab_id=project_context.virtual_lab_id,
        project_id=project_context.project_id,
        token=None,
    )

    with pytest.raises(ApiError) as excinfo:
        test_module.user_with_project_id(user_context)
    assert excinfo.value == ApiError(
        message=AuthErrorReason.PROJECT_REQUIRED,
        error_code=ApiErrorCode.NOT_AUTHORIZED,
        http_status_code=403,
    )


def test_user_with_service_admin_role_ok():
    user_context = UserContext(
        subject=uuid.UUID(TEST_USER_SUB),
        email=TEST_USER_EMAIL,
        expiration=None,
        is_authorized=True,
        is_service_admin=True,
        virtual_lab_id=VIRTUAL_LAB_ID,
        project_id=PROJECT_ID,
        token=None,
    )
    result = test_module.user_with_service_admin_role(user_context)
    assert isinstance(result, UserContext)
    assert result.is_service_admin is True


def test_user_with_service_admin_role_raises():
    user_context = UserContext(
        subject=uuid.UUID(TEST_USER_SUB),
        email=TEST_USER_EMAIL,
        expiration=None,
        is_authorized=True,
        is_service_admin=False,
        virtual_lab_id=VIRTUAL_LAB_ID,
        project_id=PROJECT_ID,
        token=None,
    )
    with pytest.raises(ApiError) as excinfo:
        test_module.user_with_service_admin_role(user_context)
    assert excinfo.value == ApiError(
        message=AuthErrorReason.ADMIN_REQUIRED,
        error_code=ApiErrorCode.NOT_AUTHORIZED,
        http_status_code=403,
    )
