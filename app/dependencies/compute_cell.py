from http import HTTPStatus
from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.config import settings
from app.dependencies.auth import UserContextDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.utils.http import make_http_request


def get_compute_cell(
    user_context: UserContextDep,
    request: Request,
) -> str:
    """Resolve the launch-system URL based on the virtual lab's compute_cell property.

    The configured ``LAUNCH_SYSTEM_URL_TEMPLATE`` may contain a subdomain placeholder.
    This function fetches the virtual lab from the virtual-lab-api and replaces the
    placeholder with ``cell-a`` or ``cell-b`` depending on the ``compute_cell``
    property.
    """
    if not user_context.virtual_lab_id:
        L.error("No virtual lab ID found")
        raise ApiError(
            message="No virtual lab ID found",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )

    vlab_url = settings.get_virtual_lab_url(user_context.virtual_lab_id)
    token = user_context.token.credentials
    http_client = request.state.http_client
    response = make_http_request(
        vlab_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
        http_client=http_client,
    )
    data = response.json()
    compute_cell = data["data"]["virtual_lab"]["compute_cell"]
    L.info("Resolved subdomain %s", compute_cell)
    return compute_cell


ComputeCellDep = Annotated[str, Depends(get_compute_cell)]
