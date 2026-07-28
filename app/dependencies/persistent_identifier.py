from http import HTTPStatus
from typing import Annotated

from fastapi import Depends

from app.errors import ApiError, ApiErrorCode
from app.schemas.persistent_identifier import (
    ORCID_URL_PREFIX,
    ROR_URL_PREFIX,
    IdentifierType,
    PersistentIdentifier,
)


def get_persistent_identifier(identifier: str) -> PersistentIdentifier:

    stripped = identifier.strip()

    if identifier.startswith(ORCID_URL_PREFIX):
        return PersistentIdentifier(
            type=IdentifierType.orcid,
            url=stripped,
        )

    if identifier.startswith(ROR_URL_PREFIX):
        return PersistentIdentifier(
            type=IdentifierType.ror,
            url=stripped,
        )

    raise ApiError(
        message=(
            f"Invalid identifier format: '{identifier}'. "
            "Expected ORCID (https://orcid.org/0000-0000-0000-000X)"
            "or ROR ID (https://ror.org/0xxxxxxxxx)"
        ),
        error_code=ApiErrorCode.INVALID_REQUEST,
        http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


PersistentIdentifierDep = Annotated[PersistentIdentifier, Depends(get_persistent_identifier)]
