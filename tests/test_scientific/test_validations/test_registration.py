"""Tests for validation outcome registration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bluecellulab.validation.base import ValidationOutcome
from obi_one.scientific.validations.registration import (
    RegisteredResult,
    register_outcome,
    register_outcomes,
)


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def sample_outcome(tmp_path):
    fig = tmp_path / "test_fig.pdf"
    fig.write_text("fake pdf")
    return ValidationOutcome(
        name="Test Validation",
        passed=True,
        details="All good.",
        figures=[fig],
    )


class TestRegisterOutcome:
    def test_registers_new_result(self, mock_client, sample_outcome, tmp_path):
        # No existing result
        mock_iterator = MagicMock()
        mock_iterator.first.return_value = None
        mock_client.search_entity.return_value = mock_iterator

        # register_entity returns entity with id
        registered_entity = MagicMock()
        registered_entity.id = "new-id-123"
        mock_client.register_entity.return_value = registered_entity

        result = register_outcome(
            client=mock_client,
            outcome=sample_outcome,
            validated_entity_id="entity-456",
            out_dir=tmp_path,
        )

        assert result.entity_id == "new-id-123"
        assert result.outcome == sample_outcome
        assert result.skipped is False
        mock_client.register_entity.assert_called_once()
        mock_client.upload_file.assert_called()  # figure + details

    def test_skips_if_already_exists(self, mock_client, sample_outcome, tmp_path):
        # Existing result found
        mock_iterator = MagicMock()
        mock_iterator.first.return_value = MagicMock()  # non-None means exists
        mock_client.search_entity.return_value = mock_iterator

        result = register_outcome(
            client=mock_client,
            outcome=sample_outcome,
            validated_entity_id="entity-456",
            out_dir=tmp_path,
            skip_if_exists=True,
        )

        assert result.skipped is True
        assert result.entity_id is None
        mock_client.register_entity.assert_not_called()

    def test_registers_even_if_exists_when_skip_disabled(
        self, mock_client, sample_outcome, tmp_path
    ):
        mock_iterator = MagicMock()
        mock_iterator.first.return_value = MagicMock()
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "forced-id"
        mock_client.register_entity.return_value = registered_entity

        result = register_outcome(
            client=mock_client,
            outcome=sample_outcome,
            validated_entity_id="entity-456",
            out_dir=tmp_path,
            skip_if_exists=False,
        )

        assert result.skipped is False
        assert result.entity_id == "forced-id"
        mock_client.register_entity.assert_called_once()

    def test_uploads_pdf_figure(self, mock_client, tmp_path):
        fig = tmp_path / "plot.pdf"
        fig.write_text("pdf content")
        outcome = ValidationOutcome(
            name="Fig Test", passed=True, details="ok", figures=[fig]
        )

        mock_iterator = MagicMock()
        mock_iterator.first.return_value = None
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "fig-id"
        mock_client.register_entity.return_value = registered_entity

        register_outcome(mock_client, outcome, "ent-1", out_dir=tmp_path)

        # Check upload_file was called with pdf content type
        upload_calls = mock_client.upload_file.call_args_list
        assert any("plot.pdf" in str(call) for call in upload_calls)

    def test_skips_unsupported_figure_format(self, mock_client, tmp_path):
        fig = tmp_path / "plot.svg"
        fig.write_text("svg content")
        outcome = ValidationOutcome(
            name="SVG Test", passed=True, details="ok", figures=[fig]
        )

        mock_iterator = MagicMock()
        mock_iterator.first.return_value = None
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "svg-id"
        mock_client.register_entity.return_value = registered_entity

        register_outcome(mock_client, outcome, "ent-1", out_dir=tmp_path)

        # upload_file should only be called for details, not for the svg figure
        for call in mock_client.upload_file.call_args_list:
            assert "plot.svg" not in str(call)


class TestRegisterOutcomes:
    def test_registers_multiple(self, mock_client, tmp_path):
        outcomes = [
            ValidationOutcome(name="Test 1", passed=True, details="ok1"),
            ValidationOutcome(name="Test 2", passed=False, details="fail2"),
        ]

        mock_iterator = MagicMock()
        mock_iterator.first.return_value = None
        mock_client.search_entity.return_value = mock_iterator

        registered_entity = MagicMock()
        registered_entity.id = "batch-id"
        mock_client.register_entity.return_value = registered_entity

        results = register_outcomes(mock_client, outcomes, "ent-1", out_dir=tmp_path)
        assert len(results) == 2
        assert all(not r.skipped for r in results)

    def test_continues_on_failure(self, mock_client, tmp_path):
        outcomes = [
            ValidationOutcome(name="Fail", passed=True, details="ok"),
            ValidationOutcome(name="Success", passed=True, details="ok"),
        ]

        mock_iterator = MagicMock()
        mock_iterator.first.return_value = None
        mock_client.search_entity.return_value = mock_iterator

        # First register fails, second succeeds
        registered_entity = MagicMock()
        registered_entity.id = "ok-id"
        mock_client.register_entity.side_effect = [
            RuntimeError("API error"),
            registered_entity,
        ]

        results = register_outcomes(mock_client, outcomes, "ent-1", out_dir=tmp_path)
        assert len(results) == 2
        # First one should have None entity_id due to error
        assert results[0].entity_id is None
        assert results[1].entity_id == "ok-id"
