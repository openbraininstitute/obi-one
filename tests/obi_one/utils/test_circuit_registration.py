"""Tests for circuit registration utility functions."""

from datetime import datetime

import pytest

from obi_one.utils.circuit_registration import get_exp_date


# --- get_exp_date ---


def test_get_exp_date_none():
    """Test that None is returned when no date is provided."""
    assert get_exp_date({}) is None
    assert get_exp_date({"experiment_date": None}) is None


def test_get_exp_date_day_month_year():
    """Test parsing of dd.mm.YYYY format."""
    result = get_exp_date({"experiment_date": "27.03.2024"})
    assert result == datetime(2024, 3, 27)


def test_get_exp_date_month_year():
    """Test parsing of 'Month, YYYY' format."""
    result = get_exp_date({"experiment_date": "November, 2024"})
    assert result == datetime(2024, 11, 1)


def test_get_exp_date_unsupported_format():
    """Test that unsupported format raises."""
    with pytest.raises(ValueError, match="not supported"):
        get_exp_date({"experiment_date": "2024-03-27"})


def test_get_exp_date_invalid_string():
    """Test that invalid date string raises."""
    with pytest.raises(ValueError, match="not supported"):
        get_exp_date({"experiment_date": "not a date"})


from obi_one.utils.circuit_registration import (
    _check_file_path,
    _check_required_contents,
    _is_on_aws_s3,
)


# --- _is_on_aws_s3 ---


def test_is_on_aws_s3_true():
    """Test that S3 paths are detected."""
    assert _is_on_aws_s3("s3://openbluebrain/some/path") is True


def test_is_on_aws_s3_case_insensitive():
    """Test that detection is case-insensitive."""
    assert _is_on_aws_s3("S3://OpenBlueBrain/some/path") is True


def test_is_on_aws_s3_false():
    """Test that local paths are not detected as S3."""
    assert _is_on_aws_s3("/local/path/to/file") is False
    assert _is_on_aws_s3("relative/path") is False


def test_is_on_aws_s3_other_bucket():
    """Test that other S3 buckets are not detected."""
    assert _is_on_aws_s3("s3://some/path") is False


# --- _check_file_path ---


def test_check_file_path_empty():
    """Test that empty path raises."""
    with pytest.raises(ValueError, match="File path missing"):
        _check_file_path("")


def test_check_file_path_local_exists(tmp_path):
    """Test that existing local path passes."""
    f = tmp_path / "test.txt"
    f.write_text("hello")
    _check_file_path(str(f))  # Should not raise


def test_check_file_path_local_not_exists():
    """Test that non-existent local path raises."""
    with pytest.raises(ValueError, match="does not exist in local file system"):
        _check_file_path("/nonexistent/path/to/file.txt")


# --- _check_required_contents ---


def test_check_required_contents_empty_list(tmp_path):
    """Test that empty contents list passes without checking."""
    _check_required_contents(str(tmp_path), [], is_directory=True)


def test_check_required_contents_directory_valid(tmp_path):
    """Test that required files in a directory pass."""
    (tmp_path / "file_a.txt").write_text("a")
    (tmp_path / "file_b.txt").write_text("b")

    _check_required_contents(
        str(tmp_path), ["file_a.txt", "file_b.txt"], is_directory=True
    )


def test_check_required_contents_directory_missing(tmp_path):
    """Test that missing file in directory raises."""
    (tmp_path / "file_a.txt").write_text("a")

    with pytest.raises(ValueError, match="not found in"):
        _check_required_contents(
            str(tmp_path), ["file_a.txt", "missing.txt"], is_directory=True
        )


def test_check_required_contents_file_valid(tmp_path):
    """Test that file name matches for non-directory check."""
    f = tmp_path / "circuit.gz"
    f.write_text("data")

    _check_required_contents(str(f), ["circuit.gz"], is_directory=False)


def test_check_required_contents_file_mismatch(tmp_path):
    """Test that file name mismatch raises for non-directory check."""
    f = tmp_path / "other.gz"
    f.write_text("data")

    with pytest.raises(ValueError, match="does not match"):
        _check_required_contents(str(f), ["circuit.gz"], is_directory=False)


from obi_one.utils.circuit_registration import _check_matrix_folder


# --- _check_matrix_folder ---


def test_check_matrix_folder_valid(tmp_path):
    """Test that a valid matrix folder passes."""
    import json

    (tmp_path / "connectivity_matrix.h5").write_text("data")
    (tmp_path / "matrix_config.json").write_text(
        json.dumps({"pop1": {"single": {"path": "connectivity_matrix.h5"}}})
    )

    _check_matrix_folder(str(tmp_path))  # Should not raise


def test_check_matrix_folder_missing_config(tmp_path):
    """Test that missing matrix_config.json raises."""
    (tmp_path / "connectivity_matrix.h5").write_text("data")

    with pytest.raises(ValueError, match="matrix_config.json missing"):
        _check_matrix_folder(str(tmp_path))


def test_check_matrix_folder_missing_referenced_file(tmp_path):
    """Test that a referenced matrix file not found raises."""
    import json

    (tmp_path / "matrix_config.json").write_text(
        json.dumps({"pop1": {"single": {"path": "missing.h5"}}})
    )

    with pytest.raises(ValueError, match="referenced in config but not found"):
        _check_matrix_folder(str(tmp_path))


def test_check_matrix_folder_nested_structure(tmp_path):
    """Test that a valid matrix folder with nested paths passes."""
    import json

    (tmp_path / "pop1" / "single").mkdir(parents=True)
    (tmp_path / "pop1" / "single" / "connectivity_matrix.h5").write_text("data")
    (tmp_path / "matrix_config.json").write_text(
        json.dumps({"pop1": {"single": {"path": "pop1/single/connectivity_matrix.h5"}}})
    )

    _check_matrix_folder(str(tmp_path))  # Should not raise


from unittest.mock import MagicMock, patch

from obi_one.utils.circuit_registration import (
    check_if_circuit_exists,
    find_agent,
    find_role,
    get_brain_region,
    get_circuit,
    get_contributions,
    get_license,
    get_parent_circuit,
    get_publications,
    get_root_circuit,
    get_subject,
)


def _mock_client_search(results):
    """Create a mock client whose search_entity returns the given results."""
    client = MagicMock()
    client.search_entity.return_value.all.return_value = results
    return client


# --- get_circuit ---


def test_get_circuit_none_name():
    """Test that None name returns None."""
    client = MagicMock()
    assert get_circuit(client, None) is None


def test_get_circuit_found():
    """Test that a single match is returned."""
    circuit = MagicMock(id="abc-123")
    client = _mock_client_search([circuit])

    result = get_circuit(client, "my_circuit")
    assert result is circuit


def test_get_circuit_not_found():
    """Test that missing circuit returns None when must_exist=False."""
    client = _mock_client_search([])
    assert get_circuit(client, "missing", must_exist=False) is None


def test_get_circuit_not_found_must_exist():
    """Test that missing circuit raises when must_exist=True."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found"):
        get_circuit(client, "missing", must_exist=True)


def test_get_circuit_multiple():
    """Test that multiple matches raises."""
    client = _mock_client_search([MagicMock(id="1"), MagicMock(id="2")])
    with pytest.raises(ValueError, match="Multiple circuits"):
        get_circuit(client, "duplicate")


# --- check_if_circuit_exists ---


def test_check_if_circuit_exists_missing_name():
    """Test that missing name raises."""
    client = MagicMock()
    with pytest.raises(ValueError, match="Circuit name missing"):
        check_if_circuit_exists(client, {})


def test_check_if_circuit_exists_already_registered():
    """Test that existing circuit raises."""
    circuit = MagicMock()
    client = _mock_client_search([circuit])
    with pytest.raises(ValueError, match="already exists"):
        check_if_circuit_exists(client, {"name": "existing"})


def test_check_if_circuit_exists_not_registered():
    """Test that non-existing circuit passes."""
    client = _mock_client_search([])
    check_if_circuit_exists(client, {"name": "new_circuit"})  # Should not raise


# --- get_root_circuit ---


def test_get_root_circuit_none():
    """Test that no root specified returns None."""
    client = _mock_client_search([])
    result = get_root_circuit(client, {"root": None})
    assert result is None


def test_get_root_circuit_found():
    """Test that root circuit is resolved."""
    circuit = MagicMock(name="root_circuit", id="root-id")
    client = _mock_client_search([circuit])
    result = get_root_circuit(client, {"root": "root_circuit"})
    assert result is circuit


# --- get_parent_circuit ---


def test_get_parent_circuit_none_no_derivation():
    """Test that no parent with no derivation type passes."""
    client = _mock_client_search([])
    result = get_parent_circuit(client, {"parent": None, "derivation_type": None})
    assert result is None


def test_get_parent_circuit_none_with_derivation_type():
    """Test that no parent with derivation type raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="requires a parent circuit"):
        get_parent_circuit(client, {"parent": None, "derivation_type": "circuit_extraction"})


def test_get_parent_circuit_found_valid_derivation():
    """Test that parent with valid derivation type passes."""
    circuit = MagicMock(name="parent_circuit", id="parent-id")
    client = _mock_client_search([circuit])
    result = get_parent_circuit(
        client, {"parent": "parent_circuit", "derivation_type": "circuit_extraction"}
    )
    assert result is circuit


def test_get_parent_circuit_found_invalid_derivation():
    """Test that parent with invalid derivation type raises."""
    circuit = MagicMock(name="parent_circuit", id="parent-id")
    client = _mock_client_search([circuit])
    with pytest.raises(ValueError, match="valid derivation type is required"):
        get_parent_circuit(
            client, {"parent": "parent_circuit", "derivation_type": "invalid_type"}
        )


# --- find_agent ---


def test_find_agent_found():
    """Test that agent is found."""
    agent = MagicMock(pref_label="John Doe")
    client = _mock_client_search([agent])
    result = find_agent(client, "John Doe", "person")
    assert result is agent


def test_find_agent_not_found():
    """Test that missing agent raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found"):
        find_agent(client, "Unknown", "person")


def test_find_agent_multiple_returns_first():
    """Test that multiple matches returns first with warning."""
    agent1 = MagicMock(pref_label="John Doe")
    agent2 = MagicMock(pref_label="John Doe")
    client = _mock_client_search([agent1, agent2])
    result = find_agent(client, "John Doe", "person")
    assert result is agent1


# --- find_role ---


def test_find_role_found():
    """Test that role is found."""
    role = MagicMock()
    role.name = "unspecified"
    client = _mock_client_search([role])
    result = find_role(client, "unspecified")
    assert result is role


def test_find_role_not_found():
    """Test that missing role raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found or multiple"):
        find_role(client, "nonexistent")


def test_find_role_multiple():
    """Test that multiple roles raises."""
    role1 = MagicMock()
    role1.name = "unspecified"
    role2 = MagicMock()
    role2.name = "unspecified"
    client = _mock_client_search([role1, role2])
    with pytest.raises(ValueError, match="not found or multiple"):
        find_role(client, "unspecified")


# --- get_subject ---


def test_get_subject_found():
    """Test that subject is resolved with matching species."""
    subject = MagicMock(name="Average rat P14", id="subj-id")
    subject.species.name = "Rattus norvegicus"
    client = _mock_client_search([subject])
    result = get_subject(client, {"subject": "Average rat P14", "species": "Rattus norvegicus"})
    assert result is subject


def test_get_subject_missing_name():
    """Test that missing subject name raises."""
    client = MagicMock()
    with pytest.raises(ValueError, match="Subject must be provided"):
        get_subject(client, {"subject": None})


def test_get_subject_not_found():
    """Test that missing subject raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found"):
        get_subject(client, {"subject": "Unknown", "species": "Rattus norvegicus"})


def test_get_subject_species_mismatch():
    """Test that species mismatch raises."""
    subject = MagicMock(name="Average rat P14")
    subject.species.name = "Mus musculus"
    client = _mock_client_search([subject])
    with pytest.raises(ValueError, match="inconsistent"):
        get_subject(client, {"subject": "Average rat P14", "species": "Rattus norvegicus"})


def test_get_subject_no_species_provided():
    """Test that missing species in metadata raises inconsistency."""
    subject = MagicMock(name="Average rat P14")
    subject.species.name = "Rattus norvegicus"
    client = _mock_client_search([subject])
    with pytest.raises(ValueError, match="inconsistent"):
        get_subject(client, {"subject": "Average rat P14"})


# --- get_brain_region ---


def test_get_brain_region_found():
    """Test that brain region is resolved."""
    region = MagicMock(name="Primary somatosensory area", id="region-id")
    client = _mock_client_search([region])
    result = get_brain_region(client, {"brain_region": "Primary somatosensory area"})
    assert result is region


def test_get_brain_region_missing_name():
    """Test that missing brain region name raises."""
    client = MagicMock()
    with pytest.raises(ValueError, match="Brain region must be provided"):
        get_brain_region(client, {"brain_region": None})


def test_get_brain_region_not_found():
    """Test that missing brain region raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found"):
        get_brain_region(client, {"brain_region": "Unknown"})


# --- get_license ---


def test_get_license_found():
    """Test that license is resolved."""
    lic = MagicMock(label="CC BY 4.0", name="Creative Commons", id="lic-id")
    client = _mock_client_search([lic])
    result = get_license(client, {"license": "CC BY 4.0"})
    assert result is lic


def test_get_license_none():
    """Test that no license returns None."""
    client = MagicMock()
    result = get_license(client, {"license": None})
    assert result is None


def test_get_license_not_found():
    """Test that missing license raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found"):
        get_license(client, {"license": "Unknown License"})


# --- get_contributions ---


def test_get_contributions_resolves_agents_and_roles():
    """Test that contributions are resolved."""
    agent = MagicMock(type="person", pref_label="John Doe", id="agent-id")
    role = MagicMock(id="role-id")
    role.name = "unspecified"

    client = MagicMock()
    # find_agent call, then find_role call
    client.search_entity.return_value.all.side_effect = [
        [agent],  # find_agent
        [role],   # find_role
    ]

    result = get_contributions(
        client, {"John Doe": {"type": "person", "role": "unspecified"}}
    )
    assert "John Doe" in result
    assert result["John Doe"]["agent"] is agent
    assert result["John Doe"]["role"] is role


# --- get_publications ---


def test_get_publications_resolves():
    """Test that publications are resolved."""
    pub = MagicMock(id="pub-id", DOI="10.1234/test")
    client = _mock_client_search([pub])

    result = get_publications(client, {"10.1234/test": {"type": "entity_source"}})
    assert "10.1234/test" in result
    assert result["10.1234/test"]["entity"] is pub
    assert result["10.1234/test"]["type"] == "entity_source"


def test_get_publications_unknown_type():
    """Test that unknown publication type raises."""
    client = MagicMock()
    with pytest.raises(ValueError, match="unknown"):
        get_publications(client, {"10.1234/test": {"type": "invalid_type"}})


def test_get_publications_not_found():
    """Test that missing publication raises."""
    client = _mock_client_search([])
    with pytest.raises(ValueError, match="not found"):
        get_publications(client, {"10.1234/test": {"type": "entity_source"}})
