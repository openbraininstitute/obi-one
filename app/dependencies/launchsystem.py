import httpx

from app.config import settings
from app.dependencies.auth import UserContextDep


def get_client(
    user_context: UserContextDep,
) -> httpx.Client:
    api_url = settings.ENTITYCORE_URL.replace(
        "entitycore", "launch-system"
    )  # TODO: Create separate entry in settings (?)

    token = user_context.token.credentials
    client = httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {token}"})

    return client
