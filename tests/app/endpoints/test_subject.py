"""Tests for the subject registration endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.models import Species

from app.application import app
from app.dependencies.entitysdk import get_client
from app.schemas.subject import normalize_name_for_comparison

_BASE = "/declared/subject"


def _make_mock_db_client(*, search_all_results=None, search_one_or_none=None):
    """Create a mock db client.

    Args:
        search_all_results: list returned by search_entity(...).all()
        search_one_or_none: value returned by search_entity(...).one_or_none()
    """
    mock_client = MagicMock()
    mock_search_result = MagicMock()
    mock_search_result.all.return_value = search_all_results or []
    mock_search_result.one_or_none.return_value = search_one_or_none
    mock_client.search_entity.return_value = mock_search_result
    return mock_client


@pytest.fixture
def mock_db_client():
    return _make_mock_db_client()


@pytest.fixture(autouse=True)
def _override_db_client(mock_db_client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_client, lambda: mock_db_client)
    yield
    app.dependency_overrides.pop(get_client, None)


VALID_SUBJECT = {
    "name": "Mouse Alpha",
    "description": "Adult male C57BL/6 mouse used in experiments",
    "species_id": str(uuid4()),
    "sex": "male",
}


class TestGetSubject:
    def test_found(self, client, mock_db_client):
        """GET returns subject when found by name."""
        existing = MagicMock()
        existing.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse Alpha",
            "description": "A mouse",
            "sex": "male",
        }
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        resp = client.get(f"{_BASE}?name=Mouse Alpha")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Mouse Alpha"

    def test_not_found(self, client):
        """GET returns 404 when subject not found."""
        resp = client.get(f"{_BASE}?name=NonExistent")

        assert resp.status_code == 404

    def test_unauthenticated(self, client_no_auth):
        resp = client_no_auth.get(f"{_BASE}?name=Mouse Alpha")
        assert resp.status_code in {401, 403}


class TestRegisterSubject:
    def test_register_new_subject(self, client, mock_db_client):
        """POST creates a new subject when no duplicate exists."""
        mock_db_client.get_entity.return_value = Species(
            id=uuid4(), name="Mus musculus", taxonomy_id="10090"
        )

        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse Alpha",
            "description": "Adult male C57BL/6 mouse used in experiments",
            "sex": "male",
        }
        mock_db_client.register_entity.return_value = mock_registered

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 201
        assert resp.json()["name"] == "Mouse Alpha"
        mock_db_client.register_entity.assert_called_once()

    def test_duplicate_exact_name_returns_409(self, client, mock_db_client):
        """POST returns 409 when exact same name already exists."""
        existing = MagicMock()
        existing.id = uuid4()
        existing.name = "Mouse Alpha"
        mock_db_client.search_entity.return_value.all.return_value = [existing]

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 409
        assert "already exists" in resp.json()["message"]
        mock_db_client.register_entity.assert_not_called()

    def test_duplicate_different_case_returns_409(self, client, mock_db_client):
        """POST returns 409 when same name with different casing exists."""
        existing = MagicMock()
        existing.id = uuid4()
        existing.name = "mouse alpha"  # lowercase in DB
        mock_db_client.search_entity.return_value.all.return_value = [existing]

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 409
        mock_db_client.register_entity.assert_not_called()

    def test_duplicate_different_separators_returns_409(self, client, mock_db_client):
        """POST returns 409 when name differs only by separators (spaces, hyphens, etc)."""
        existing = MagicMock()
        existing.id = uuid4()
        existing.name = "Mouse-Alpha"  # hyphen instead of space
        mock_db_client.search_entity.return_value.all.return_value = [existing]

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 409
        mock_db_client.register_entity.assert_not_called()

    def test_duplicate_no_separators_returns_409(self, client, mock_db_client):
        """POST returns 409 when concatenated version of name exists."""
        existing = MagicMock()
        existing.id = uuid4()
        existing.name = "MouseAlpha"  # no space
        mock_db_client.search_entity.return_value.all.return_value = [existing]

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 409
        mock_db_client.register_entity.assert_not_called()

    def test_no_duplicate_with_different_name(self, client, mock_db_client):
        """POST succeeds when search returns non-matching candidates."""
        candidate = MagicMock()
        candidate.id = uuid4()
        candidate.name = "Mouse Beta"  # different name
        mock_db_client.search_entity.return_value.all.return_value = [candidate]
        mock_db_client.get_entity.return_value = Species(
            id=uuid4(), name="Mus musculus", taxonomy_id="10090"
        )

        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse Alpha",
            "description": "Adult male C57BL/6 mouse used in experiments",
            "sex": "male",
        }
        mock_db_client.register_entity.return_value = mock_registered

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 201
        mock_db_client.register_entity.assert_called_once()

    def test_missing_required_fields(self, client):
        """POST with missing fields returns 422."""
        resp = client.post(f"{_BASE}", json={"name": "Mouse Alpha"})
        assert resp.status_code == 422

    def test_invalid_sex(self, client):
        """POST with invalid sex value returns 422."""
        data = {**VALID_SUBJECT, "sex": "invalid_value"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422

    def test_age_period_required_with_age_value(self, client):
        """POST with age_value but no age_period returns 422."""
        data = {**VALID_SUBJECT, "age_value": 86400}  # 1 day in seconds
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422

    def test_age_value_and_range_conflict(self, client):
        """POST with both age_value and age_min returns 422."""
        data = {
            **VALID_SUBJECT,
            "age_value": 86400,
            "age_min": 43200,
            "age_max": 172800,
            "age_period": "postnatal",
        }
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422

    def test_unauthenticated(self, client_no_auth):
        resp = client_no_auth.post(f"{_BASE}", json=VALID_SUBJECT)
        assert resp.status_code in {401, 403}


class TestNameValidation:
    """Tests for name validation rules."""

    def test_name_too_short(self, client):
        """Name must be at least 3 characters."""
        data = {**VALID_SUBJECT, "name": "AB"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422
        assert "at least 3 characters" in str(resp.json())

    def test_purely_numeric_name_rejected(self, client):
        """Purely numeric names are rejected."""
        data = {**VALID_SUBJECT, "name": "12345"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422
        assert "purely numeric" in str(resp.json())

    def test_blocklist_word_rejected(self, client):
        """Names containing blocklisted words are rejected."""
        data = {**VALID_SUBJECT, "name": "My test subject"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422
        assert "disallowed word" in str(resp.json())

    def test_blocklist_phrase_rejected(self, client):
        """Names containing blocklisted phrases are rejected."""
        data = {**VALID_SUBJECT, "name": "please delete me now"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422
        assert "disallowed phrase" in str(resp.json())

    def test_whitespace_normalization(self, client, mock_db_client):
        """Leading/trailing/multiple spaces are collapsed."""
        mock_db_client.get_entity.return_value = Species(
            id=uuid4(), name="Mus musculus", taxonomy_id="10090"
        )
        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse Alpha",
            "description": "Adult male C57BL/6 mouse used in experiments",
            "sex": "male",
        }
        mock_db_client.register_entity.return_value = mock_registered

        data = {**VALID_SUBJECT, "name": "  Mouse   Alpha  "}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 201

    def test_special_characters_allowed(self, client, mock_db_client):
        """Special characters are now allowed (rule 6 excluded)."""
        mock_db_client.get_entity.return_value = Species(
            id=uuid4(), name="Mus musculus", taxonomy_id="10090"
        )
        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse@Lab#1",
            "description": "Subject with special chars in name",
            "sex": "male",
        }
        mock_db_client.register_entity.return_value = mock_registered

        data = {
            **VALID_SUBJECT,
            "name": "Mouse@Lab#1",
            "description": "Subject with special chars in name",
        }
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 201

    def test_description_too_short(self, client):
        """Description must be at least 10 characters."""
        data = {**VALID_SUBJECT, "description": "Short"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422
        assert "at least 10 characters" in str(resp.json())

    def test_description_blocklist_rejected(self, client):
        """Descriptions containing blocklisted words are rejected."""
        data = {**VALID_SUBJECT, "description": "This is just a placeholder description"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422
        assert "disallowed word" in str(resp.json())

    def test_empty_name_after_strip(self, client):
        """Name that becomes empty after stripping is rejected."""
        data = {**VALID_SUBJECT, "name": "   "}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422


class TestNormalizeNameForComparison:
    """Unit tests for the normalization function used in duplicate detection."""

    def test_basic_normalization(self):
        assert normalize_name_for_comparison("Average Rat") == "averagerat"

    def test_case_insensitive(self):
        assert normalize_name_for_comparison("AVERAGE RAT") == "averagerat"

    def test_strips_hyphens(self):
        assert normalize_name_for_comparison("Average-Rat") == "averagerat"

    def test_strips_underscores(self):
        assert normalize_name_for_comparison("Average_Rat") == "averagerat"

    def test_strips_special_chars(self):
        assert normalize_name_for_comparison("Average@Rat!") == "averagerat"

    def test_concatenated_form(self):
        assert normalize_name_for_comparison("AverageRat") == "averagerat"

    def test_all_variants_equal(self):
        """All variants of the same name should produce the same normalized form."""
        variants = [
            "Average Rat",
            "average rat",
            "AverageRat",
            "Average-rat",
            "Average_rat",
            "AVERAGE RAT",
            "average-RAT",
            " Average  Rat ",
        ]
        normalized = {normalize_name_for_comparison(v) for v in variants}
        assert len(normalized) == 1
        assert normalized == {"averagerat"}

    def test_digits_preserved(self):
        assert normalize_name_for_comparison("Mouse 01") == "mouse01"

    def test_empty_string(self):
        assert not normalize_name_for_comparison("")

    def test_only_special_chars(self):
        assert not normalize_name_for_comparison("---")
