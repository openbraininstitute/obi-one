from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import httpx2
import pytest
from entitysdk.common import ProjectContext
from entitysdk.exception import EntitySDKError
from entitysdk.models.circuit import Circuit

from obi_one.db_sdk.assets import asset_download_url, open_asset_h5

TINY_CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")
API_URL = "http://entitycore/api/entitycore"
STORAGE = "http://storage/"


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


def fake_client(circuit_dir: Path = TINY_CIRCUIT_DIR, *, redirect: bool = True) -> MagicMock:
    """An entitysdk-shaped client whose HTTP goes to ``storage_transport``."""
    client = MagicMock()
    client.api_url = API_URL
    client.project_context = ProjectContext(virtual_lab_id=uuid4(), project_id=uuid4())
    client._token_manager.get_token.return_value = "token"
    client._http_client = httpx2.Client(transport=storage_transport(circuit_dir, redirect=redirect))
    return client


class TestAssetDownloadUrl:
    def test_returns_the_redirect_target_without_following_it(self):
        client = fake_client()
        url = asset_download_url(
            client,
            entity_id=uuid4(),
            entity_type=Circuit,
            asset_id=uuid4(),
            asset_path="S1nonbarrel_neurons/nodes.h5",
        )
        assert url == f"{STORAGE}S1nonbarrel_neurons/nodes.h5"

    def test_sends_the_project_headers(self):
        client = fake_client()
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx2.Response(307, headers={"location": "http://storage/x"})

        client._http_client = httpx2.Client(transport=httpx2.MockTransport(handler))
        asset_download_url(
            client, entity_id=uuid4(), entity_type=Circuit, asset_id=uuid4(), asset_path="x"
        )
        assert seen["project-id"] == str(client.project_context.project_id)
        assert seen["virtual-lab-id"] == str(client.project_context.virtual_lab_id)

    def test_without_a_project_context_only_the_token_is_sent(self):
        client = fake_client()
        client.project_context = None
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx2.Response(307, headers={"location": "http://storage/x"})

        client._http_client = httpx2.Client(transport=httpx2.MockTransport(handler))
        asset_download_url(
            client, entity_id=uuid4(), entity_type=Circuit, asset_id=uuid4(), asset_path="x"
        )
        assert seen["authorization"] == "Bearer token"
        assert "project-id" not in seen

    def test_a_project_without_a_virtual_lab_sends_only_the_project_id(self):
        client = fake_client()
        client.project_context = ProjectContext(project_id=uuid4())
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx2.Response(307, headers={"location": "http://storage/x"})

        client._http_client = httpx2.Client(transport=httpx2.MockTransport(handler))
        asset_download_url(
            client, entity_id=uuid4(), entity_type=Circuit, asset_id=uuid4(), asset_path="x"
        )
        assert seen["project-id"] == str(client.project_context.project_id)
        assert "virtual-lab-id" not in seen

    def test_no_redirect_is_an_error(self):
        with pytest.raises(EntitySDKError, match="Expected a redirect"):
            asset_download_url(
                fake_client(redirect=False),
                entity_id=uuid4(),
                entity_type=Circuit,
                asset_id=uuid4(),
                asset_path="x",
            )


class TestOpenAssetH5:
    def test_reads_a_dataset_of_the_remote_file(self):
        with open_asset_h5(
            fake_client(),
            entity_id=uuid4(),
            entity_type=Circuit,
            asset_id=uuid4(),
            asset_path="S1nonbarrel_neurons/nodes.h5",
            size=(TINY_CIRCUIT_DIR / "S1nonbarrel_neurons/nodes.h5").stat().st_size,
        ) as h5:
            library = h5["nodes/S1nonbarrel_neurons/0/@library/model_template"].asstr()[:]
        assert "hoc:cADpyr_L6BPC" in set(library)
