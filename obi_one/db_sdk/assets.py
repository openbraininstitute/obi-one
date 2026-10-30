"""Read part of a file of a directory asset without downloading the whole file."""

from uuid import UUID

import h5py
from entitysdk.client import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models.entity import Entity
from entitysdk.route import get_assets_endpoint

from obi_one.utils.http_range_file import HttpRangeFile


def asset_download_url(
    client: Client,
    *,
    entity_id: UUID,
    entity_type: type[Entity],
    asset_id: UUID,
    asset_path: str,
) -> str:
    """Return the storage URL of one file of a directory asset.

    entitycore answers a download request with a redirect to a presigned storage URL.
    entitysdk follows that redirect itself (``fetch_file``, ``fetch_content``) and has no
    method that returns the URL, which a partial read needs. Until entitysdk offers one,
    this function asks entitycore directly, with the client's own token, headers and HTTP
    client, so authentication, timeouts and connection pooling stay the same.

    The URL is signed and expires soon: use it right away and never store or log it.

    Args:
        client: entitysdk client.
        entity_id: Entity that owns the asset.
        entity_type: Type of that entity, e.g. ``Circuit``.
        asset_id: The directory asset.
        asset_path: Path of the file inside the asset.

    Returns:
        The presigned storage URL.

    Raises:
        EntitySDKError: entitycore answered without a redirect.
    """
    endpoint = get_assets_endpoint(
        api_url=client.api_url, entity_type=entity_type, entity_id=entity_id, asset_id=asset_id
    )
    headers = {"Authorization": f"Bearer {client._token_manager.get_token()}"}  # ruff: ignore[private-member-access]
    if client.project_context:
        headers["project-id"] = str(client.project_context.project_id)
        if client.project_context.virtual_lab_id:
            headers["virtual-lab-id"] = str(client.project_context.virtual_lab_id)
    response = client._http_client.get(  # ruff: ignore[private-member-access]
        f"{endpoint}/download",
        params={"asset_path": asset_path},
        headers=headers,
        follow_redirects=False,
    )
    if not response.is_redirect:
        msg = f"Expected a redirect to storage for {asset_path}, got {response.status_code}"
        raise EntitySDKError(msg)
    return str(response.headers["location"])


def open_asset_h5(
    client: Client,
    *,
    entity_id: UUID,
    entity_type: type[Entity],
    asset_id: UUID,
    asset_path: str,
    size: int,
) -> h5py.File:
    """Open an HDF5 file of a directory asset, fetching only the bytes h5py reads.

    HDF5 files can be read in any order: h5py reads the few headers that lead to a dataset,
    then the dataset itself. Each of those reads becomes a ``Range`` request to storage,
    so reading one small dataset of a file of several GB costs a few MB.

    Args:
        client: entitysdk client.
        entity_id: Entity that owns the asset.
        entity_type: Type of that entity, e.g. ``Circuit``.
        asset_id: The directory asset.
        asset_path: Path of the HDF5 file inside the asset.
        size: File size in bytes, from ``Client.list_directory``.

    Returns:
        An open, read-only ``h5py.File``; close it, for example with ``with``.

    It fails with ``EntitySDKError`` when entitycore does not redirect to storage, and with
    ``OSError`` (when opening or reading) when storage does not serve byte ranges or
    ``size`` is wrong. Callers usually fall back to a full download.
    """
    url = asset_download_url(
        client,
        entity_id=entity_id,
        entity_type=entity_type,
        asset_id=asset_id,
        asset_path=asset_path,
    )
    return h5py.File(HttpRangeFile(url, client._http_client, size), "r")  # ruff: ignore[private-member-access]
