"""Tests for test result registration."""

from unittest.mock import MagicMock

import httpx
import pytest
from bluecellulab.validation.base import TestResult
from entitysdk.types import AssetLabel, ContentType

from obi_one.scientific.validations.registration import (
    ValidationResultAlreadyExistsError,
    ValidationResultPermissionError,
    register_outcome,
    register_outcomes,
)


def _forbidden_error():
    request = httpx.Request("PATCH", "https://example.test/validation-result")
    response = httpx.Response(status_code=403, request=request)
    return httpx.HTTPStatusError("forbidden", request=request, response=response)


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def sample_test_result(tmp_path):
    fig = tmp_path / "test_fig.pdf"
    fig.write_text("fake pdf")
    return TestResult(
        name="Test Validation",
        passed=True,
        details="All good.",
        figures=[fig],
    )


class TestRegisterOutcome:
    def test_registers_new_result(self, mock_client, sample_test_result, tmp_path):
        # No existing result
        mock_iterator = MagicMock()
        mock_iterator.all.return_value = []
        mock_client.search_entity.return_value = mock_iterator

        # register_entity returns entity with id
        registered_entity = MagicMock()
        registered_entity.id = "new-id-123"
        mock_client.register_entity.return_value = registered_entity

        result = register_outcome(
            client=mock_client,
            test_result=sample_test_result,
            validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
            out_dir=tmp_path,
        )

        assert result.entity_id == "new-id-123"
        assert result.test_result == sample_test_result
        assert result.skipped is False
        mock_client.register_entity.assert_called_once()
        mock_client.upload_file.assert_called()  # figure + details

    def test_skips_if_already_exists(self, mock_client, sample_test_result, tmp_path):
        # Existing result found
        existing_entity = MagicMock()
        existing_entity.id = "existing-id"
        mock_iterator = MagicMock()
        mock_iterator.all.return_value = [existing_entity]
        mock_client.search_entity.return_value = mock_iterator

        result = register_outcome(
            client=mock_client,
            test_result=sample_test_result,
            validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
            out_dir=tmp_path,
            overwrite_existing=False,
        )

        assert result.skipped is True
        assert result.entity_id == "existing-id"
        mock_client.register_entity.assert_not_called()

    def test_errors_if_multiple_results_exist(self, mock_client, sample_test_result, tmp_path):
        existing_entities = [MagicMock(id="existing-id-1"), MagicMock(id="existing-id-2")]
        mock_iterator = MagicMock()
        mock_iterator.all.return_value = existing_entities
        mock_client.search_entity.return_value = mock_iterator

        with pytest.raises(ValidationResultAlreadyExistsError):
            register_outcome(
                client=mock_client,
                test_result=sample_test_result,
                validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
                out_dir=tmp_path,
                overwrite_existing=True,
            )

        mock_client.register_entity.assert_not_called()

    def test_uploads_pdf_figure(self, mock_client, tmp_path):
        fig = tmp_path / "plot.pdf"
        fig.write_text("pdf content")
        test_result = TestResult(name="Fig Test", passed=True, details="ok", figures=[fig])

        mock_iterator = MagicMock()
        mock_iterator.all.return_value = []
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "fig-id"
        mock_client.register_entity.return_value = registered_entity

        register_outcome(
            mock_client, test_result, "5e8f4a2b-6c1d-47f0-8a9e-2b3c4d5e6f70", out_dir=tmp_path
        )

        # Check upload_file was called with pdf content type
        upload_calls = mock_client.upload_file.call_args_list
        assert any("plot.pdf" in str(call) for call in upload_calls)

    def test_skips_unsupported_figure_format(self, mock_client, tmp_path):
        fig = tmp_path / "plot.svg"
        fig.write_text("svg content")
        test_result = TestResult(name="SVG Test", passed=True, details="ok", figures=[fig])

        mock_iterator = MagicMock()
        mock_iterator.all.return_value = []
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "svg-id"
        mock_client.register_entity.return_value = registered_entity

        register_outcome(
            mock_client, test_result, "5e8f4a2b-6c1d-47f0-8a9e-2b3c4d5e6f70", out_dir=tmp_path
        )

        # upload_file should only be called for details, not for the svg figure
        for call in mock_client.upload_file.call_args_list:
            assert "plot.svg" not in str(call)


class TestRegisterOutcomes:
    def test_registers_multiple(self, mock_client, tmp_path):
        test_results = [
            TestResult(name="Test 1", passed=True, details="ok1"),
            TestResult(name="Test 2", passed=False, details="fail2"),
        ]

        mock_iterator = MagicMock()
        mock_iterator.all.return_value = []
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "batch-id"
        mock_client.register_entity.return_value = registered_entity

        results = register_outcomes(
            mock_client, test_results, "5e8f4a2b-6c1d-47f0-8a9e-2b3c4d5e6f70", out_dir=tmp_path
        )
        assert len(results) == 2
        assert all(not r.skipped for r in results)

    def test_continues_on_failure(self, mock_client, tmp_path):
        test_results = [
            TestResult(name="Fail", passed=True, details="ok"),
            TestResult(name="Success", passed=True, details="ok"),
        ]

        mock_iterator = MagicMock()
        mock_iterator.all.return_value = []
        mock_client.search_entity.return_value = mock_iterator

        # First register fails, second succeeds
        registered_entity = MagicMock()
        registered_entity.id = "ok-id"
        mock_client.register_entity.side_effect = [
            RuntimeError("API error"),
            registered_entity,
        ]

        results = register_outcomes(
            mock_client, test_results, "5e8f4a2b-6c1d-47f0-8a9e-2b3c4d5e6f70", out_dir=tmp_path
        )
        assert len(results) == 2
        # First one should have None entity_id due to error
        assert results[0].entity_id is None
        assert results[1].entity_id == "ok-id"


class TestOverwriteExisting:
    def _existing(self):
        existing = MagicMock()
        existing.id = "existing-id"
        return existing

    def test_updates_in_place_and_replaces_assets(self, mock_client, sample_test_result, tmp_path):
        search_iter = MagicMock()
        search_iter.all.return_value = [self._existing()]
        mock_client.search_entity.return_value = search_iter

        # Two old assets: one replaceable figure (deleted) and one unrelated (kept).
        fig_asset = MagicMock(id="fig-asset")
        fig_asset.label = AssetLabel.validation_result_figure
        other_asset = MagicMock(id="other-asset")
        other_asset.label = AssetLabel.morphology
        assets_iter = MagicMock()
        assets_iter.all.return_value = [fig_asset, other_asset]
        mock_client.get_entity_assets.return_value = assets_iter

        result = register_outcome(
            client=mock_client,
            test_result=sample_test_result,
            validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
            out_dir=tmp_path,
            overwrite_existing=True,
        )

        assert result.updated is True
        assert result.entity_id == "existing-id"
        mock_client.update_entity.assert_called_once()
        mock_client.register_entity.assert_not_called()
        # Only the replaceable asset is deleted, not the unrelated one.
        mock_client.delete_asset.assert_called_once()
        # New figure + details are re-uploaded.
        assert mock_client.upload_file.call_count >= 1

    def test_permission_error_on_forbidden_update(self, mock_client, sample_test_result, tmp_path):
        search_iter = MagicMock()
        search_iter.all.return_value = [self._existing()]
        mock_client.search_entity.return_value = search_iter
        mock_client.update_entity.side_effect = _forbidden_error()

        with pytest.raises(ValidationResultPermissionError, match="Not authorized"):
            register_outcome(
                client=mock_client,
                test_result=sample_test_result,
                validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
                out_dir=tmp_path,
                overwrite_existing=True,
            )

    def test_non_forbidden_http_error_propagates(self, mock_client, sample_test_result, tmp_path):
        search_iter = MagicMock()
        search_iter.all.return_value = [self._existing()]
        mock_client.search_entity.return_value = search_iter
        request = httpx.Request("PATCH", "https://example.test/x")
        server_error = httpx.HTTPStatusError(
            "boom", request=request, response=httpx.Response(500, request=request)
        )
        mock_client.update_entity.side_effect = server_error

        with pytest.raises(httpx.HTTPStatusError):
            register_outcome(
                client=mock_client,
                test_result=sample_test_result,
                validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
                out_dir=tmp_path,
                overwrite_existing=True,
            )


class TestAssetUpload:
    def test_png_figure_uses_image_content_type(self, mock_client, tmp_path):
        png = tmp_path / "trace.png"
        png.write_text("fake png")
        test_result = TestResult(name="PNG Test", passed=True, details="", figures=[png])
        search_iter = MagicMock()
        search_iter.all.return_value = []
        mock_client.search_entity.return_value = search_iter
        registered = MagicMock(id="png-id")
        mock_client.register_entity.return_value = registered

        register_outcome(
            client=mock_client,
            test_result=test_result,
            validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
            out_dir=tmp_path,
        )

        # details is empty, so the only upload is the png figure.
        mock_client.upload_file.assert_called_once()
        kwargs = mock_client.upload_file.call_args.kwargs
        assert kwargs["file_content_type"] == ContentType.image_png

    def test_missing_figure_is_skipped(self, mock_client, tmp_path):
        missing = tmp_path / "does_not_exist.pdf"
        test_result = TestResult(name="Missing Fig", passed=True, details="", figures=[missing])
        search_iter = MagicMock()
        search_iter.all.return_value = []
        mock_client.search_entity.return_value = search_iter
        mock_client.register_entity.return_value = MagicMock(id="m-id")

        register_outcome(
            client=mock_client,
            test_result=test_result,
            validated_entity_id="3f4e8f5e-2a6e-4b40-9a1d-1f4e5f6a7b8c",
            out_dir=tmp_path,
        )

        mock_client.upload_file.assert_not_called()
