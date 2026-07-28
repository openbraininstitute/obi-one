from http import HTTPStatus
from typing import Annotated

from fastapi import Depends

from app.errors import ApiError, ApiErrorCode
from app.schemas.persistent_identifier import (
    ORCID_URL_PREFIX,
    ROR_URL_PREFIX,
    OrcidPersistentIdentifier,
    RorPersistentIdentifier,
)
from app.types import IdentifierType


def get_persistent_identifier(
    identifier: str,
) -> OrcidPersistentIdentifier | RorPersistentIdentifier:
    stripped = identifier.strip()

    if stripped.startswith(ORCID_URL_PREFIX):
        return OrcidPersistentIdentifier(kind=IdentifierType.orcid, url=stripped)

    if stripped.startswith(ROR_URL_PREFIX):
        return RorPersistentIdentifier(kind=IdentifierType.ror, url=stripped)

    raise ApiError(
        message=(
            f"Invalid identifier format: '{identifier}'. "
            "Expected an ORCID URL (https://orcid.org/0000-0000-0000-000X) "
            "or a ROR URL (https://ror.org/0xxxxxxxxx)."
        ),
        error_code=ApiErrorCode.INVALID_REQUEST,
        http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


PersistentIdentifierDep = Annotated[
    OrcidPersistentIdentifier | RorPersistentIdentifier,
    Depends(get_persistent_identifier),
]
