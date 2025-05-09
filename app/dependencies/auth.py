import hashlib
import threading
import time
from typing import Annotated
from uuid import UUID

import cachetools
import httpx
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from app.config import settings
from app.errors import ApiError, ApiErrorCode, AuthErrorReason
from app.logger import L
from app.schemas.auth import (
    CacheKey,
    DecodedToken,
    UserContext,
    UserContextWithProjectId,
    UserInfoResponse,
)
from app.schemas.base import OptionalProjectContext
from app.utils.common import is_ascii
from app.utils.http import deserialize_response, make_http_request

# auto_error=False because of https://github.com/fastapi/fastapi/issues/10177
AuthHeader: HTTPBearer = HTTPBearer(auto_error=False)

KEYCLOAK_GROUPS_URL = f"{settings.KEYCLOAK_URL}/protocol/openid-connect/userinfo"


def _get_cache_key(
    *,
    project_context: OptionalProjectContext,
    token: HTTPAuthorizationCredentials,
    **_,
) -> CacheKey:
    """Return the cache key for the given parameters.

    The cache key includes also virtual-lab-id and project-id to force a new request to KeyCloak
    when they change. This should avoid using a stale cache when a new project is created or
    assigned to the user, and the user switches to that project.
    """
    return CacheKey(
        virtual_lab_id=project_context.virtual_lab_id,
        project_id=project_context.project_id,
        scheme=token.scheme.lower(),
        token_digest=hashlib.sha256(token.credentials.encode()).hexdigest(),
    )


def _get_cache_ttu(_key: CacheKey, value: UserContext, now: float) -> float:
    """Calculate the expiration time of an item at the time of insertion into the cache.

    Args:
        _key: cache key.
        value: cache value.
        now: current value of the timer function.
    """
    expiration = now + settings.AUTH_CACHE_MAX_TTL
    if value.is_authorized and value.expiration and value.expiration > now:
        # consider the token expiration only if the UserContext si authorized
        expiration = min(expiration, value.expiration)
    return expiration


@cachetools.cached(
    cache=cachetools.TLRUCache(
        maxsize=settings.AUTH_CACHE_MAXSIZE,
        ttu=_get_cache_ttu,
        timer=time.time,
    ),
    key=_get_cache_key,
    lock=threading.Lock(),
    info=settings.AUTH_CACHE_INFO,
)
def _check_user_info(
    *,
    project_context: OptionalProjectContext,
    token: HTTPAuthorizationCredentials,
    http_client: httpx.Client,
) -> UserContext:
    """Retrieve the user info from KeyCloak and check the correctness of ProjectContext.

    Note that the result is cached, but exceptions are NOT cached.
    """
    decoded = DecodedToken.from_jwt(token)
    if decoded and decoded.exp and decoded.exp < time.time():
        # expired token, no need to call KeyCloak
        return UserContext(
            subject=decoded.sub,
            email=decoded.email,
            expiration=decoded.exp,
            is_authorized=False,
            virtual_lab_id=project_context.virtual_lab_id,
            project_id=project_context.project_id,
            auth_error_reason=AuthErrorReason.AUTH_TOKEN_EXPIRED,
            token=None,
        )

    http_status_errors = {
        401: AuthErrorReason.NOT_AUTHENTICATED_USER,
        403: AuthErrorReason.NOT_AUTHORIZED_USER,
    }
    response = make_http_request(
        KEYCLOAK_GROUPS_URL,
        method="GET",
        headers={"Authorization": f"{token.scheme} {token.credentials}"},
        http_client=http_client,
        ignored_errors=set(http_status_errors),
    )

    if response.status_code in http_status_errors:
        return UserContext(
            subject=decoded.sub if decoded else None,
            email=decoded.email if decoded else None,
            expiration=decoded.exp if decoded else None,
            is_authorized=False,
            virtual_lab_id=project_context.virtual_lab_id,
            project_id=project_context.project_id,
            auth_error_reason=http_status_errors[response.status_code],
            token=None,
        )

    user_info_response = deserialize_response(response, model_class=UserInfoResponse)
    is_authorized = user_info_response.is_authorized_for(
        virtual_lab_id=project_context.virtual_lab_id,
        project_id=project_context.project_id,
    )
    is_service_admin = user_info_response.is_service_admin(settings.APP_NAME)
    user_context = UserContext(
        subject=user_info_response.sub,
        email=user_info_response.email,
        expiration=decoded.exp if decoded else None,
        is_authorized=is_authorized,
        is_service_admin=is_service_admin,
        virtual_lab_id=project_context.virtual_lab_id,
        project_id=project_context.project_id,
        auth_error_reason=AuthErrorReason.NOT_AUTHORIZED_PROJECT if not is_authorized else None,
        token=token if is_authorized else None,
    )

    if not user_context.is_authorized:
        L.info(
            "User <%(email)s> attempted to use: "
            "virtual-lab-id=%(virtual_lab_id)s, project-id=%(project_id)s "
            "but they're only a member of %(groups)s",
            {
                "email": user_context.email,
                "virtual_lab_id": project_context.virtual_lab_id,
                "project_id": project_context.project_id,
                "groups": sorted(user_info_response.groups),
            },
        )

    return user_context


def user_verified(
    project_context: Annotated[OptionalProjectContext, Header()],
    token: Annotated[HTTPAuthorizationCredentials | None, Depends(AuthHeader)],
    request: Request,
) -> UserContext:
    """Ensure that the user is authenticated and authorized.

    The user must be a member of the virtual_lab_id and project_id claimed in the headers.
    If only the virtual_lab_id specified, the user must be a member of the virtual_lab_id.
    If neither is specified, it's enough that the auth token is valid.
    """
    if settings.APP_DISABLE_AUTH:
        L.warning("Authentication is disabled: admin role granted, vlab and proj not verified")
        return UserContext(
            subject=UUID(int=0),
            email=None,
            expiration=None,
            is_authorized=True,
            is_service_admin=True,
            virtual_lab_id=project_context.virtual_lab_id,
            project_id=project_context.project_id,
            token=token,
        )

    if not token:
        raise ApiError(
            message=AuthErrorReason.AUTH_TOKEN_MISSING,
            error_code=ApiErrorCode.NOT_AUTHENTICATED,
            http_status_code=401,
        )
    if not token.credentials or not is_ascii(token.credentials):
        # non-ascii headers would raise an error in httpx when calling KeyCloak
        raise ApiError(
            message=AuthErrorReason.AUTH_TOKEN_INVALID,
            error_code=ApiErrorCode.NOT_AUTHENTICATED,
            http_status_code=401,
        )

    user_context = _check_user_info(
        project_context=project_context,
        token=token,
        http_client=request.state.http_client,
    )

    if not user_context.is_authorized:
        match user_context.auth_error_reason:
            case AuthErrorReason.NOT_AUTHORIZED_USER | AuthErrorReason.NOT_AUTHORIZED_PROJECT:
                raise ApiError(
                    message=user_context.auth_error_reason,
                    error_code=ApiErrorCode.NOT_AUTHORIZED,
                    http_status_code=403,
                )
            case _:
                raise ApiError(
                    message=user_context.auth_error_reason or AuthErrorReason.UNKNOWN,
                    error_code=ApiErrorCode.NOT_AUTHENTICATED,
                    http_status_code=401,
                )

    return user_context


def user_with_project_id(user_context: "UserContextDep") -> UserContextWithProjectId:
    """Ensure that the authenticated user has valid virtual_lab_id and project_id."""
    if not user_context.virtual_lab_id or not user_context.project_id:
        raise ApiError(
            message=AuthErrorReason.PROJECT_REQUIRED,
            error_code=ApiErrorCode.NOT_AUTHORIZED,
            http_status_code=403,
        )
    return UserContextWithProjectId.model_validate(user_context, from_attributes=True)


def user_with_service_admin_role(user_context: "UserContextDep") -> UserContext:
    """Ensure that the authenticated user has a service admin role."""
    if not user_context.is_service_admin:
        raise ApiError(
            message=AuthErrorReason.ADMIN_REQUIRED,
            error_code=ApiErrorCode.NOT_AUTHORIZED,
            http_status_code=403,
        )
    return user_context


UserContextDep = Annotated[UserContext, Depends(user_verified)]
UserContextWithProjectIdDep = Annotated[UserContextWithProjectId, Depends(user_with_project_id)]
