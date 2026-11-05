from pathlib import Path
from uuid import uuid4

import h5py
import httpx2
import pytest
from entitysdk.client import Client
from entitysdk.common import ProjectContext
from entitysdk.config import settings as entitysdk_settings
from entitysdk.exception import EntitySDKError
from entitysdk.models.circuit import Circuit

from obi_one.db_sdk.assets import asset_download_url, asset_range_file

TINY_CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")
API_URL = "http://entitycore/api/entitycore"
STORAGE = "http://storage/"
PROJECT = ProjectContext(virtual_lab_id=uuid4(), project_id=uuid4())


def storage_transport(circuit_dir: Path, *, redirect: bool = True) -> httpx2.MockTransport:
    """entitycore's ``/download`` redirect plus an S3-like storage serving byte ranges."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "entitycore":
            if not redirect:
                return httpx2.Response(200, content=b"not a redirect")
            asset_path = request.url.params["asset_path"]
            assert request.headers["authorization"] == "Bearer token"
            return httpx2.Response(307, headers={"location": f"{STORAGE}{asset_path}"})
        blob = (circuit_dir / request.url.path.lstrip("/")).read_bytes()
        if request.method == "HEAD":  # refused on presigned URLs signed for GET
            return httpx2.Response(403)
        start, end = request.headers["range"].removeprefix("bytes=").split("-")
        return httpx2.Response(206, content=blob[int(start) : int(end) + 1])

    return httpx2.MockTransport(handler)


def fake_client(
    circuit_dir: Path = TINY_CIRCUIT_DIR,
    *,
    redirect: bool = True,
    transport: httpx2.MockTransport | None = None,
    project_context: ProjectContext | None = PROJECT,
) -> Client:
    """A real entitysdk client whose HTTP goes to ``storage_transport`` (or ``transport``).

    A real ``Client``, not a mock: ``asset_download_url`` reaches into the client's
    internals, so a rename in entitysdk must fail here, not in production.
    """
    return Client(
        api_url=API_URL,
        project_context=project_context,
        token_manager="token",  # ruff: ignore[hardcoded-password-func-arg]
        http_client=httpx2.Client(
            transport=transport or storage_transport(circuit_dir, redirect=redirect)
        ),
    )


def _download_url(client: Client, asset_path: str = "x") -> str:
    return asset_download_url(
        client, entity_id=uuid4(), entity_type=Circuit, asset_id=uuid4(), asset_path=asset_path
    )


def _recording_transport(seen: dict) -> httpx2.MockTransport:
    """Redirects every request, keeping its headers and extensions in ``seen``."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(request.headers)
        seen["timeout"] = request.extensions["timeout"]
        return httpx2.Response(307, headers={"location": "http://storage/x"})

    return httpx2.MockTransport(handler)


class TestAssetDownloadUrl:
    def test_returns_the_redirect_target_without_following_it(self):
        url = _download_url(fake_client(), "S1nonbarrel_neurons/nodes.h5")
        assert url == f"{STORAGE}S1nonbarrel_neurons/nodes.h5"

    def test_sends_the_project_headers(self):
        seen = {}
        _download_url(fake_client(transport=_recording_transport(seen)))
        assert seen["project-id"] == str(PROJECT.project_id)
        assert seen["virtual-lab-id"] == str(PROJECT.virtual_lab_id)

    def test_without_a_project_context_only_the_token_is_sent(self):
        seen = {}
        _download_url(fake_client(transport=_recording_transport(seen), project_context=None))
        assert seen["authorization"] == "Bearer token"
        assert "project-id" not in seen

    def test_a_project_without_a_virtual_lab_sends_only_the_project_id(self):
        seen = {}
        project = ProjectContext(project_id=uuid4())
        _download_url(fake_client(transport=_recording_transport(seen), project_context=project))
        assert seen["project-id"] == str(project.project_id)
        assert "virtual-lab-id" not in seen

    def test_the_request_uses_the_timeouts_entitysdk_uses(self):
        seen = {}
        _download_url(fake_client(transport=_recording_transport(seen)))
        assert seen["timeout"] == {
            "connect": entitysdk_settings.connect_timeout,
            "read": entitysdk_settings.read_timeout,
            "write": entitysdk_settings.write_timeout,
            "pool": entitysdk_settings.pool_timeout,
        }

    def test_no_redirect_is_an_error(self):
        with pytest.raises(EntitySDKError, match="Expected a redirect"):
            _download_url(fake_client(redirect=False))

    def test_redirect_without_location_is_an_error(self):
        transport = httpx2.MockTransport(lambda _request: httpx2.Response(307))
        with pytest.raises(EntitySDKError, match="Expected a redirect"):
            _download_url(fake_client(transport=transport))

    def test_a_network_error_is_an_entitysdk_error_like_entitysdk_requests(self):
        def fail(_request: httpx2.Request) -> httpx2.Response:
            msg = "no route"
            raise httpx2.ConnectError(msg)

        with pytest.raises(EntitySDKError, match="Request error"):
            _download_url(fake_client(transport=httpx2.MockTransport(fail)))


class TestAssetRangeFile:
    def test_h5py_reads_a_dataset_of_the_remote_file(self):
        remote = asset_range_file(
            fake_client(),
            entity_id=uuid4(),
            entity_type=Circuit,
            asset_id=uuid4(),
            asset_path="S1nonbarrel_neurons/nodes.h5",
            size=(TINY_CIRCUIT_DIR / "S1nonbarrel_neurons/nodes.h5").stat().st_size,
        )
        with remote, h5py.File(remote, "r") as h5:
            library = h5["nodes/S1nonbarrel_neurons/0/@library/model_template"].asstr()[:]
        assert "hoc:cADpyr_L6BPC" in set(library)
        assert remote.closed
