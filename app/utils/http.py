from http import HTTPStatus

import httpx
from pydantic import BaseModel, ValidationError

from app.errors import ApiError, ApiErrorCode
from app.logger import L


def make_http_request(
    url: str,
    *,
    method: str,
    json: dict | None = None,
    parameters: dict | None = None,
    headers: dict | None = None,
    http_client: httpx.Client,
    ignored_errors: set[int] | None = None,
) -> httpx.Response:
    """Make a HTTP request.

    Args:
        url: url of the remote endpoint.
        method: request method.
        json: json request payload.
        parameters: query parameters.
        headers: request headers.
        http_client: instance of httpx.Client.
        ignored_errors: status_code errors that should not raise an error.

    Returns:
        the httpc.Response instance.
    """
    try:
        response = http_client.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            params=parameters,
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        L.warning("HTTP request error in %s %s: %r", method, url, e)
        raise ApiError(
            message="HTTP request error",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from e
    ignored_errors = ignored_errors or set()
    if not response.is_success and response.status_code not in ignored_errors:
        L.warning("HTTP status error %s in %s %s", response.status_code, method, url)
        raise ApiError(
            message=f"HTTP status error {response.status_code}",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    return response


def deserialize_response[T: BaseModel](response: httpx.Response, model_class: type[T]) -> T:
    """Deserialize the response using a Pydantic model, or raise an error."""
    try:
        return model_class.model_validate_json(response.content)
    except ValidationError as e:
        raise ApiError(
            message=f"{model_class.__class__.__name__} validation error",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from e
