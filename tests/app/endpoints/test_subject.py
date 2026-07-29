"""Tests for the subject registration endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.models import Species

from app.application import app
from app.dependencies.entitysdk import get_client
from app.schemas.subject import normalize_name_for_comparison

_BASE = "/declared/subject"

VALID_SUBJECT = {
    "name": "Mouse Alpha",
    "description": "Adult male C57BL/6 mouse used in experiments",
    "species_id": str(uuid4()),
    "sex": "male",
    "age_value": 86400,
    "age_period": "postnatal",
}


def _search_result(*, results=None, one_or_none=None):
    """Build a search_entity return value that supports iteration and one_or_none()."""
    results = list(results or [])
    mock = MagicMock()
    mock.__iter__ = lambda _self: iter(results)
    mock.one_or_none.return_value = one_or_none
    return mock


def _make_mock_db_client(*, search_results=None, search_one_or_none=None):
    mock_client = MagicMock()
    mock_client.search_entity.return_value = _search_result(
        results=search_results, one_or_none=search_one_or_none
    )
    return mock_client


def _stub_successful_register(mock_db_client, *, name="Mouse Alpha", description=None):
    mock_db_client.get_entity.return_value = Species(
        id=uuid4(), name="Mus musculus", taxonomy_id="10090"
    )
    mock_registered = MagicMock()
    mock_registered.model_dump.return_value = {
        "id": str(uuid4()),
        "name": name,
        "description": description or VALID_SUBJECT["description"],
        "sex": "male",
    }
    mock_db_client.register_entity.return_value = mock_registered


def _existing_subject(*, name):
    existing = MagicMock()
    existing.id = uuid4()
    existing.name = name
    return existing


@pytest.fixture
def mock_db_client():
    return _make_mock_db_client()


@pytest.fixture(autouse=True)
def _override_db_client(mock_db_client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_client, lambda: mock_db_client)
    yield
    app.dependency_overrides.pop(get_client, None)


def test_get_subject_found(client, mock_db_client):
    existing = MagicMock()
    existing.model_dump.return_value = {
        "id": str(uuid4()),
        "name": "Mouse Alpha",
        "description": "A mouse",
        "sex": "male",
    }
    mock_db_client.search_entity.return_value = _search_result(one_or_none=existing)

    resp = client.get(f"{_BASE}?name=Mouse Alpha")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Mouse Alpha"


def test_get_subject_not_found(client):
    resp = client.get(f"{_BASE}?name=NonExistent")
    assert resp.status_code == 404


def test_get_unauthenticated(client_no_auth):
    resp = client_no_auth.get(f"{_BASE}?name=Mouse Alpha")
    assert resp.status_code in {401, 403}


def test_register_new_subject(client, mock_db_client):
    _stub_successful_register(mock_db_client)

    resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

    assert resp.status_code == 201
    assert resp.json()["name"] == "Mouse Alpha"
    mock_db_client.register_entity.assert_called_once()


@pytest.mark.parametrize(
    "existing_name",
    ["Mouse Alpha", "mouse alpha", "Mouse-Alpha", "MouseAlpha"],
)
def test_register_duplicate_returns_409(client, mock_db_client, existing_name):
    mock_db_client.search_entity.return_value = _search_result(
        results=[_existing_subject(name=existing_name)]
    )

    resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

    assert resp.status_code == 409
    assert "already exists" in resp.json()["message"]
    mock_db_client.register_entity.assert_not_called()


def test_register_no_duplicate_with_different_name(client, mock_db_client):
    mock_db_client.search_entity.return_value = _search_result(
        results=[_existing_subject(name="Mouse Beta")]
    )
    _stub_successful_register(mock_db_client)

    resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

    assert resp.status_code == 201
    mock_db_client.register_entity.assert_called_once()


def test_register_missing_required_fields(client):
    resp = client.post(f"{_BASE}", json={"name": "Mouse Alpha"})
    assert resp.status_code == 422


def test_register_invalid_sex(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "sex": "invalid_value"})
    assert resp.status_code == 422


def test_register_age_period_required_with_age_value(client):
    resp = client.post(
        f"{_BASE}",
        json={k: v for k, v in VALID_SUBJECT.items() if k != "age_period"},
    )
    assert resp.status_code == 422


def test_register_unauthenticated(client_no_auth):
    resp = client_no_auth.post(f"{_BASE}", json=VALID_SUBJECT)
    assert resp.status_code in {401, 403}


def test_name_too_short(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": "AB"})
    assert resp.status_code == 422
    assert "at least 3 characters" in str(resp.json())


def test_purely_numeric_name_rejected(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": "12345"})
    assert resp.status_code == 422
    assert "purely numeric" in str(resp.json())


def test_blocklist_word_rejected(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": "My test subject"})
    assert resp.status_code == 422
    assert "disallowed word" in str(resp.json())


def test_blocklist_phrase_rejected(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": "please delete me now"})
    assert resp.status_code == 422
    assert "disallowed phrase" in str(resp.json())


def test_whitespace_normalization(client, mock_db_client):
    _stub_successful_register(mock_db_client)

    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": "  Mouse   Alpha  "})
    assert resp.status_code == 201


def test_special_characters_allowed(client, mock_db_client):
    _stub_successful_register(
        mock_db_client, name="Mouse@Lab#1", description="Subject with special chars in name"
    )

    data = {
        **VALID_SUBJECT,
        "name": "Mouse@Lab#1",
        "description": "Subject with special chars in name",
    }
    resp = client.post(f"{_BASE}", json=data)
    assert resp.status_code == 201


def test_description_too_short(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "description": "Short"})
    assert resp.status_code == 422
    assert "at least 10 characters" in str(resp.json())


def test_description_blocklist_rejected(client):
    resp = client.post(
        f"{_BASE}", json={**VALID_SUBJECT, "description": "This is just a placeholder description"}
    )
    assert resp.status_code == 422
    assert "disallowed word" in str(resp.json())


def test_empty_name_after_strip(client):
    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": "   "})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Average Rat", "averagerat"),
        ("AVERAGE RAT", "averagerat"),
        ("Average-Rat", "averagerat"),
        ("Average_Rat", "averagerat"),
        ("Average@Rat!", "averagerat"),
        ("AverageRat", "averagerat"),
        ("Mouse 01", "mouse01"),
        ("", ""),
        ("---", ""),
    ],
)
def test_normalize_name_for_comparison(name, expected):
    assert normalize_name_for_comparison(name) == expected


def test_normalize_name_all_variants_equal():
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
    assert normalized == {"averagerat"}
