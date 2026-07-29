"""Tests for the subject registration endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.models import Species, Strain, Subject

from app.application import app
from app.dependencies.entitysdk import get_client
from app.endpoints.subject import _find_duplicate_subject_name
from app.schemas.subject import normalize_name, split_name

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


def _existing_subject(*, name, subject_id=None):
    existing = MagicMock()
    existing.id = subject_id or uuid4()
    existing.name = name
    return existing


def _ilike_pattern_for(name: str) -> str:
    return "*" + "?".join(split_name(name)) + "*"


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
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject, query={"name": "Mouse Alpha"}
    )


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
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject,
        query={"name__ilike": "*mouse?alpha*"},
    )


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
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject,
        query={"name__ilike": "*mouse?alpha*"},
    )


def test_register_no_duplicate_with_different_name(client, mock_db_client):
    mock_db_client.search_entity.return_value = _search_result(
        results=[_existing_subject(name="Mouse Beta")]
    )
    _stub_successful_register(mock_db_client)

    resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

    assert resp.status_code == 201
    mock_db_client.register_entity.assert_called_once()


def test_register_ilike_returns_multiple_candidates_one_matches(client, mock_db_client):
    """ILIKE can return broad matches; only normalized equality yields 409."""
    matching_id = uuid4()
    mock_db_client.search_entity.return_value = _search_result(
        results=[
            _existing_subject(name="Mouse Beta"),
            _existing_subject(name="mouse-alpha", subject_id=matching_id),
            _existing_subject(name="Mouse Gamma"),
        ]
    )

    resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

    assert resp.status_code == 409
    assert str(matching_id) in resp.json()["message"]
    mock_db_client.register_entity.assert_not_called()


def test_register_ilike_empty_results_creates_subject(client, mock_db_client):
    mock_db_client.search_entity.return_value = _search_result(results=[])
    _stub_successful_register(mock_db_client)

    resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

    assert resp.status_code == 201
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject,
        query={"name__ilike": "*mouse?alpha*"},
    )


@pytest.mark.parametrize(
    ("name", "expected_ilike"),
    [
        ("Mouse Alpha", "*mouse?alpha*"),
        ("SingleWord", "*singleword*"),
        ("Three Word Name", "*three?word?name*"),
    ],
)
def test_register_builds_expected_ilike_pattern(client, mock_db_client, name, expected_ilike):
    _stub_successful_register(mock_db_client, name=name)

    resp = client.post(f"{_BASE}", json={**VALID_SUBJECT, "name": name})

    assert resp.status_code == 201
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject,
        query={"name__ilike": expected_ilike},
    )


def test_register_with_strain_and_weight(client, mock_db_client):
    species_id = uuid4()
    strain_id = uuid4()
    species = Species(id=species_id, name="Mus musculus", taxonomy_id="10090")
    strain = Strain(id=strain_id, name="C57BL/6", taxonomy_id="10090", species_id=species_id)

    mock_db_client.get_entity.side_effect = [species, strain]
    mock_registered = MagicMock()
    mock_registered.model_dump.return_value = {
        "id": str(uuid4()),
        "name": "Mouse Alpha",
        "description": VALID_SUBJECT["description"],
        "sex": "male",
        "weight": 25.5,
    }
    mock_db_client.register_entity.return_value = mock_registered

    resp = client.post(
        f"{_BASE}",
        json={
            **VALID_SUBJECT,
            "species_id": str(species_id),
            "strain_id": str(strain_id),
            "weight": 25.5,
        },
    )

    assert resp.status_code == 201
    assert mock_db_client.get_entity.call_count == 2
    registered_subject = mock_db_client.register_entity.call_args.kwargs["entity"]
    assert registered_subject.species == species
    assert registered_subject.strain == strain
    assert registered_subject.weight == pytest.approx(25.5)


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


def test_register_missing_age_value(client):
    resp = client.post(
        f"{_BASE}",
        json={k: v for k, v in VALID_SUBJECT.items() if k != "age_value"},
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
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject,
        query={"name__ilike": "*mouse?alpha*"},
    )


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


def test_find_duplicate_subject_name_empty_normalized_returns_none(mock_db_client):
    assert _find_duplicate_subject_name(mock_db_client, "---") is None
    mock_db_client.search_entity.assert_not_called()


def test_find_duplicate_subject_name_uses_ilike_and_compares_normalized(mock_db_client):
    match = _existing_subject(name="Average-Rat")
    mock_db_client.search_entity.return_value = _search_result(
        results=[_existing_subject(name="Average Mouse"), match]
    )

    found = _find_duplicate_subject_name(mock_db_client, "Average Rat")

    assert found is match
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=Subject,
        query={"name__ilike": _ilike_pattern_for("Average Rat")},
    )


def test_find_duplicate_subject_name_no_normalized_match(mock_db_client):
    mock_db_client.search_entity.return_value = _search_result(
        results=[_existing_subject(name="Average Mouse")]
    )

    assert _find_duplicate_subject_name(mock_db_client, "Average Rat") is None


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
def test_normalize_name(name, expected):
    assert normalize_name(name) == expected


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
    normalized = {normalize_name(v) for v in variants}
    assert normalized == {"averagerat"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Mouse Alpha", ["mouse", "alpha"]),
        ("Average-Rat", ["average", "rat"]),
        ("Average_rat", ["average", "rat"]),
        ("AverageRat", ["averagerat"]),
        ("Three Word Name", ["three", "word", "name"]),
    ],
)
def test_split_name(name, expected):
    assert split_name(name) == expected
