from typing import Annotated

import httpx
from fastapi import Depends
from starlette.requests import Request

from app.config import settings
from app.dependencies.auth import UserContextDep
from app.logger import L


def _resolve_launch_system_url(
    user_context: UserContextDep,
    http_client: httpx.Client,
) -> str:
    """Resolve the launch-system URL based on the virtual lab's compute_cell property.

    Fetches the virtual lab from the virtual-lab-api and checks its ``compute_cell``
    property.  When the property is ``"cell_b"``, every occurrence of ``"cell-a"`` in
    the configured ``LAUNCH_SYSTEM_URL`` is replaced with ``"cell-b"``.  In all other
    cases (property absent, ``"cell_a"``, or fetch failure) the URL is returned
    unchanged.
    """
    api_url = settings.LAUNCH_SYSTEM_URL

    if not user_context.virtual_lab_id:
        return api_url

    try:
        vlab_url = (
            f"{settings.VIRTUAL_LAB_API_URL}/virtual-labs/{user_context.virtual_lab_id}"
        )
        token = user_context.token.credentials
        response = http_client.get(
            vlab_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.is_success:
            data = response.json()
            compute_cell = (
                data.get("data", {}).get("virtual_lab", {}).get("compute_cell")
            )
            if compute_cell in ("cell_b", "CELL_B"):
                api_url = api_url.replace("cell-a", "cell-b")
                L.info("Using compute cell-b for launch-system: %s", api_url)
    except Exception:
        L.warning(
            "Failed to fetch virtual lab compute_cell, using default launch-system URL"
        )

    return api_url


def get_client(
    user_context: UserContextDep,
    request: Request,
) -> httpx.Client:
    http_client = request.state.http_client
    api_url = _resolve_launch_system_url(user_context, http_client)
    token = user_context.token.credentials
    client = httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {token}"})

    return client


LaunchSystemClientDep = Annotated[httpx.Client, Depends(get_client)]
