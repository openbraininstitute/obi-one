"""Tests for finding where an asset's bytes are served from."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from entitysdk.common import ProjectContext
from entitysdk.models import ExtracellularRecording
from entitysdk.types import AssetLabel, ContentType

from obi_one.core.exception import OBIONEError
from obi_one.db_sdk import db_sdk
from obi_one.db_sdk.db_sdk import get_asset_url, get_extracellular_recording_channel_options

API_URL = "https://entitycore"
STORAGE_URL = "https://storage/signed"


def database(*, project_context=None) -> MagicMock:
    client = MagicMock(api_url=API_URL, project_context=project_context)
    client._token_manager.get_token.return_value = "token"
    return client


def answering(response: httpx.Response) -> MagicMock:
    stream = MagicMock()
    stream.return_value.__enter__.return_value = response
    return stream


def recording() -> ExtracellularRecording:
    return ExtracellularRecording.model_construct(id=uuid4())


class TestGetAssetUrl:
    def test_it_is_where_the_download_redirects(self):
        redirect = httpx.Response(307, headers={"location": STORAGE_URL})
        with patch.object(db_sdk.httpx, "stream", answering(redirect)):
            url = get_asset_url(
                db_client=database(), entity=recording(), asset=MagicMock(id=uuid4())
            )

        assert url == STORAGE_URL

    def test_the_request_carries_the_users_session(self):
        context = ProjectContext(project_id=uuid4(), virtual_lab_id=uuid4())
        stream = answering(httpx.Response(307, headers={"location": STORAGE_URL}))
        with patch.object(db_sdk.httpx, "stream", stream):
            get_asset_url(
                db_client=database(project_context=context),
                entity=recording(),
                asset=MagicMock(id=uuid4()),
            )

        headers = stream.call_args.kwargs["headers"]
        assert stream.call_args.args[1].endswith("/download")
        assert headers["Authorization"] == "Bearer token"
        assert headers["project-id"] == str(context.project_id)

    def test_an_asset_that_is_not_redirected_is_an_error(self):
        with (
            patch.object(db_sdk.httpx, "stream", answering(httpx.Response(200))),
            pytest.raises(OBIONEError, match="not served from elsewhere"),
        ):
            get_asset_url(db_client=database(), entity=recording(), asset=MagicMock(id=uuid4()))


class TestChannelOptions:
    def test_the_nwb_asset_is_read_through_its_url(self):
        client = database()
        client.get_entity.return_value = recording()
        with (
            patch.object(db_sdk, "get_asset_url", return_value=STORAGE_URL) as get_url,
            patch.object(db_sdk, "HttpRangeFile") as range_file,
            patch.object(db_sdk.h5py, "File") as h5_file,
            patch.object(db_sdk, "read_channel_options", return_value=["option"]) as read,
        ):
            options = get_extracellular_recording_channel_options(
                recording_id=uuid4(), db_client=client
            )

        assert options == ["option"]
        assert range_file.call_args.args[0] == STORAGE_URL
        assert get_url.call_args.kwargs["entity"] is client.get_entity.return_value
        assert client.select_assets.call_args.kwargs["selection"] == {
            "content_type": ContentType.application_nwb,
            "label": AssetLabel.nwb,
        }
        read.assert_called_once_with(h5_file.return_value.__enter__.return_value)
