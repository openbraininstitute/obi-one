from typing import Annotated, Self
from uuid import UUID

import jwt
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from app.errors import AuthErrorReason
from app.logger import L


class CacheKey(BaseModel):
    """Cache key for UserContext."""

    model_config = ConfigDict(frozen=True)
    virtual_lab_id: UUID | None
    project_id: UUID | None
    scheme: str
    token_digest: str


class UserContextBase(BaseModel):
    model_config = ConfigDict(frozen=True)
    subject: UUID | None
    email: str | None
    expiration: float | None
    is_authorized: bool
    is_service_admin: bool = False
    auth_error_reason: AuthErrorReason | None = None
    token: Annotated[HTTPAuthorizationCredentials | None, Field(exclude=True)]


class UserContext(UserContextBase):
    """User Context."""

    virtual_lab_id: UUID | None = None
    project_id: UUID | None = None


class UserContextWithProjectId(UserContextBase):
    """User Context with valid virtual_lab_id and project_id."""

    virtual_lab_id: UUID
    project_id: UUID


class DecodedToken(BaseModel):
    """Decoded JWT token.

    Only a subset of the claims is extracted.
    """

    sub: UUID
    exp: float | None = None
    email: str | None = None

    @classmethod
    def from_jwt(cls, token: HTTPAuthorizationCredentials) -> Self | None:
        try:
            # the signature can be ignored because the token will be validated with KeyCloak
            decoded = jwt.decode(token.credentials, options={"verify_signature": False})
            return cls.model_validate(decoded)
        except Exception as e:  # noqa: BLE001
            L.info("Unable to decode token as JWT [%s]", e)
        return None


class UserInfoResponse(BaseModel):
    """UserInfoResponse model received from KeyCloak.

    Built from a KeyCloak response that should look like:

    {
        "email": "john.doe@example.com",
        "email_verified": false,
        "family_name": "Doe",
        "given_name": "John",
        "groups": [
            "/BBP-USERS",
            "/proj/$vlab_id/$project_id/admin",
            ...
            "/vlab/$vlab_id/admin",
            ...
        ],
        "name": "John Doe",
        "preferred_username": "johndoe",
        "sub": "83e509d1-d579-4d7e-bfe7-a0cf96ac17bf"
    }
    """

    sub: UUID
    name: str
    email: str
    groups: set[str] = set()

    def is_service_admin(self, service_name: str) -> bool:
        """Return True if admin for the specified service."""
        return not self.groups.isdisjoint(
            [
                f"/service/{service_name}/admin",
                "/service/*/admin",
            ]
        )

    def is_authorized_for(self, virtual_lab_id: UUID | None, project_id: UUID | None) -> bool:
        """Return True if authorized for the specified virtual_lab_id and project_id."""
        match (virtual_lab_id, project_id):
            case (None, None):
                # virtual_lab_id and project_id are not specified
                return True
            case (None, UUID()):
                # project_id cannot be specified without virtual_lab_id
                return False
            case (UUID(), None):
                return not self.groups.isdisjoint(
                    [
                        f"/vlab/{virtual_lab_id}/admin",
                        f"/vlab/{virtual_lab_id}/member",
                    ]
                )
            case _:
                return not self.groups.isdisjoint(
                    [
                        f"/proj/{virtual_lab_id}/{project_id}/admin",
                        f"/proj/{virtual_lab_id}/{project_id}/member",
                    ]
                )
