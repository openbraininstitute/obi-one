"""Read part of a file of a directory asset without downloading the whole file."""

from http import HTTPStatus
from uuid import UUID

from entitysdk.client import Client
from entitysdk.config import settings as entitysdk_settings
from entitysdk.exception import EntitySDKError
from entitysdk.models.entity import Entity
from entitysdk.route import get_assets_endpoint
from entitysdk.utils.http import HTTPStatusError, HTTPTimeout, RequestError

from obi_one.utils.http_range_file import HttpRangeFile

# Same timeouts as entitysdk's own requests.
ENTITYSDK_TIMEOUT = HTTPTimeout(
    connect=entitysdk_settings.connect_timeout,
    read=entitysdk_settings.read_timeout,
    write=entitysdk_settings.write_timeout,
    pool=entitysdk_settings.pool_timeout,
)


def is_not_found(err: EntitySDKError) -> bool:
    """Whether the request failed because the file is not there (HTTP 404).

    entitysdk raises ``EntitySDKError`` for every failure, chained from the HTTP error;
    only the chained response tells a missing file from an outage or a refused token.
    """
    cause = err.__cause__
    return isinstance(cause, HTTPStatusError) and cause.response.status_code == HTTPStatus.NOT_FOUND


def asset_download_url(
    client: Client,
    *,
    entity_id: UUID,
    entity_type: type[Entity],
    asset_id: UUID,
    asset_path: str,
) -> str:
    """Return the presigned storage URL of one file of a directory asset.

    entitysdk follows the download redirect itself and has no method that returns the
    URL, so this asks entitycore directly with the client's token, headers and timeouts.
    The URL is signed and short-lived: use it at once, never store or log it.

    Args:
        client: entitysdk client.
        entity_id: Entity that owns the asset.
        entity_type: Type of that entity, e.g. ``Circuit``.
        asset_id: The directory asset.
        asset_path: Path of the file inside the asset.

    Raises:
        EntitySDKError: No redirect, or the request failed (network error, timeout).
    """
    # TODO(entitysdk): private members. Use a public "download URL" method once entitysdk
    # has one; tests/obi_one/db_sdk/test_assets.py uses a real Client so a rename fails CI.
    endpoint = get_assets_endpoint(
        api_url=client.api_url, entity_type=entity_type, entity_id=entity_id, asset_id=asset_id
    )
    headers = {"Authorization": f"Bearer {client._token_manager.get_token()}"}  # ruff: ignore[private-member-access]
    if client.project_context:
        headers["project-id"] = str(client.project_context.project_id)
        if client.project_context.virtual_lab_id:
            headers["virtual-lab-id"] = str(client.project_context.virtual_lab_id)
    try:
        response = client._http_client.get(  # ruff: ignore[private-member-access]
            f"{endpoint}/download",
            params={"asset_path": asset_path},
            headers=headers,
            follow_redirects=False,
            timeout=ENTITYSDK_TIMEOUT,
        )
    except RequestError as err:
        msg = f"Request error: {err}"
        raise EntitySDKError(msg) from err
    location = response.headers.get("location")
    if not response.is_redirect or location is None:
        msg = f"Expected a redirect to storage for {asset_path}, got {response.status_code}"
        raise EntitySDKError(msg)
    return location


def asset_range_file(
    client: Client,
    *,
    entity_id: UUID,
    entity_type: type[Entity],
    asset_id: UUID,
    asset_path: str,
    size: int,
) -> HttpRangeFile:
    """Open one file of a directory asset as a file object that fetches bytes on demand.

    For ``h5py.File(asset_range_file(...), "r")``: each h5py read becomes one ``Range``
    request, so one small dataset of a multi-GB file costs a few MB. Read a large dataset
    with ``read_contiguous_dataset`` so the request does not hold h5py's lock.

    Args:
        client: entitysdk client.
        entity_id: Entity that owns the asset.
        entity_type: Type of that entity, e.g. ``Circuit``.
        asset_id: The directory asset.
        asset_path: Path of the file inside the asset.
        size: File size in bytes, from ``Client.list_directory``.

    Returns:
        The file object. Nothing is fetched before the first read; close it after use.
        A read raises ``OSError`` when storage does not serve ranges or ``size`` is wrong.
    """
    url = asset_download_url(
        client,
        entity_id=entity_id,
        entity_type=entity_type,
        asset_id=asset_id,
        asset_path=asset_path,
    )
    return HttpRangeFile(url, client._http_client, size)  # ruff: ignore[private-member-access]
