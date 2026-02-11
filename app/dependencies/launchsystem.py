from http import HTTPStatus
from typing import Annotated

import httpx
from fastapi import Depends
from starlette.requests import Request

from app.config import settings
from app.dependencies.auth import UserContextDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.utils.http import make_http_request

COMPUTE_CELL_PLACEHOLDER = "cell-X"
COMPUTE_CELL_MAP = {
    "CELL_A": "cell-a",
    "CELL_B": "cell-b",
}
COMPUTE_CELL_DEFAULT = "cell-a"


def _resolve_launch_system_url(
    user_context: UserContextDep,
    http_client: httpx.Client,
) -> str:
    """Resolve the launch-system URL based on the virtual lab's compute_cell property.

    The configured ``LAUNCH_SYSTEM_URL`` may contain a ``cell-X`` placeholder.  This
    function fetches the virtual lab from the virtual-lab-api and replaces the
    placeholder with ``cell-a`` or ``cell-b`` depending on the ``compute_cell``
    property.
    """
    api_url = settings.LAUNCH_SYSTEM_URL

    if COMPUTE_CELL_PLACEHOLDER not in api_url:
        return api_url

    compute_cell_resolved = COMPUTE_CELL_DEFAULT

    if user_context.virtual_lab_id:
        vlab_url = settings.get_virtual_lab_url(user_context.virtual_lab_id)
        token = user_context.token.credentials
        response = make_http_request(
            vlab_url,
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
            http_client=http_client,
        )
        data = response.json()
        compute_cell = data["data"]["virtual_lab"]["compute_cell"]
        if compute_cell in COMPUTE_CELL_MAP:
            compute_cell_resolved = COMPUTE_CELL_MAP[compute_cell]
        else:
            L.error("Unknown compute cell: %s", compute_cell)
            raise ApiError(
                message=f"Unknown compute cell: {compute_cell}",
                error_code=ApiErrorCode.INVALID_REQUEST,
                http_status_code=HTTPStatus.BAD_REQUEST,
            )
        api_url = api_url.replace(COMPUTE_CELL_PLACEHOLDER, compute_cell_resolved)
        L.info("Resolved launch-system URL: %s", api_url)
        return api_url

    L.error("No virtual lab ID found")
    raise ApiError(
        message="No virtual lab ID found",
        error_code=ApiErrorCode.INVALID_REQUEST,
        http_status_code=HTTPStatus.BAD_REQUEST,
    )


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
