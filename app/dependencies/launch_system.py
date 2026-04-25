from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends

from app.config import settings
from app.dependencies.auth import UserContextDep


def get_client(
    user_context: UserContextDep,
) -> httpx.Client:
    token = user_context.token.credentials
    return httpx.Client(
        base_url=settings.LAUNCH_SYSTEM_URL,
        headers={"Authorization": f"Bearer {token}"},
        verify=not settings.LAUNCH_SYSTEM_DISABLE_SSL_VERIFY,
    )


LaunchSystemClientDep = Annotated[httpx.Client, Depends(get_client)]


async def get_async_client(
    user_context: UserContextDep,
) -> AsyncIterator[httpx.AsyncClient]:
    token = user_context.token.credentials
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(
        base_url=settings.LAUNCH_SYSTEM_URL,
        headers=headers,
        verify=not settings.LAUNCH_SYSTEM_DISABLE_SSL_VERIFY,
        timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
    ) as client:
        yield client


LaunchSystemAsyncClientDep = Annotated[httpx.AsyncClient, Depends(get_async_client)]
