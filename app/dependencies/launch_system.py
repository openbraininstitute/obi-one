from typing import Annotated

import httpx
from fastapi import Depends

from app.config import settings
from app.dependencies.auth import UserContextDep


def get_client(
    user_context: UserContextDep,
) -> httpx.Client:
    token = user_context.token.credentials  # ty:ignore[unresolved-attribute]
    return httpx.Client(
        base_url=settings.LAUNCH_SYSTEM_URL,
        headers={"Authorization": f"Bearer {token}"},
        verify=not settings.LAUNCH_SYSTEM_DISABLE_SSL_VERIFY,
    )


LaunchSystemClientDep = Annotated[httpx.Client, Depends(get_client)]
