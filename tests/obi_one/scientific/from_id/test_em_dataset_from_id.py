from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from obi_one.config import settings
from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.em_dataset_from_id import (
    EMDataSetFromID,
    _configure_caveclient_retries,
)

_MODULE = "obi_one.scientific.from_id.em_dataset_from_id"


def _make_dataset():
    return EMDataSetFromID(id_str="dataset-1", auth_token="fake-token")  # noqa: S106


def _http_error(status=503):
    response = Mock()
    response.status_code = status
    return requests.HTTPError(f"{status} Server Error", response=response)


class TestRetryConfiguration:
    def test_configure_caveclient_retries_from_settings(self):
        """Retry session defaults should be sourced from settings.cave_client_config."""
        with patch(f"{_MODULE}.set_session_defaults") as mock_set_defaults:
            _configure_caveclient_retries()

        cfg = settings.cave_client_config
        mock_set_defaults.assert_called_once_with(
            max_retries=cfg.max_retries,
            backoff_factor=cfg.retry_backoff_factor,
            backoff_max=cfg.retry_backoff_max,
            status_forcelist=cfg.retry_status_forcelist,
        )

    def test_make_cave_client_passes_entity_metadata(self):
        """The CAVEclient should be built from the entity's datastack/url + auth token."""
        ds = _make_dataset()
        entity = SimpleNamespace(cave_datastack="stack", cave_client_url="http://cave")

        with (
            patch.object(EMDataSetFromID, "entity", return_value=entity),
            patch(f"{_MODULE}.CAVEclient") as mock_cave,
        ):
            ds._make_cave_client(Mock(), cave_version=7)

        mock_cave.assert_called_once_with(
            "stack",
            server_address="http://cave",
            auth_token="fake-token",  # noqa: S106
        )
        assert mock_cave.return_value.version == 7


class TestGracefulMaterializeErrors:
    @pytest.mark.parametrize(
        ("method_name", "kwargs", "make_error"),
        [
            ("get_versions", {}, lambda: _http_error(503)),
            ("get_tables", {"cave_version": 3}, lambda: _http_error(503)),
            ("get_versions", {}, lambda: requests.exceptions.ConnectionError("boom")),
        ],
        ids=["get_versions-http-503", "get_tables-http-503", "get_versions-connection"],
    )
    def test_request_errors_wrapped_in_obi_error(self, method_name, kwargs, make_error):
        """Transient request failures surface as a clean OBIONEError."""
        ds = _make_dataset()
        client = Mock()
        getattr(client.materialize, method_name).side_effect = make_error()

        with (
            patch.object(EMDataSetFromID, "_make_cave_client", return_value=client),
            pytest.raises(OBIONEError, match="temporarily unavailable"),
        ):
            getattr(ds, method_name)(**kwargs)

    def test_non_request_errors_propagate_unchanged(self):
        """Errors unrelated to the request layer must not be masked as OBIONEError."""
        ds = _make_dataset()
        client = Mock()
        client.materialize.get_versions.side_effect = ValueError("unrelated")

        with (
            patch.object(EMDataSetFromID, "_make_cave_client", return_value=client),
            pytest.raises(ValueError, match="unrelated"),
        ):
            ds.get_versions()
