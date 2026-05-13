"""Tests for circuit registration utility functions."""

import json as json_module
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from obi_one.utils.circuit_registration import (
    _check_file_path,
    _check_matrix_folder,
    _check_required_contents,
    _is_on_aws_s3,
    check_if_circuit_exists,
    find_agent,
    find_role,
    get_brain_region,
    get_circuit,
    get_contributions,
    get_exp_date,
    get_license,
    get_parent_circuit,
    get_publications,
    get_root_circuit,
    get_subject,
    register_asset,
    register_circuit,
    register_contributions,
    register_derivation,
    register_publication_links,
)

from tests.utils import CIRCUIT_DIR

# --- get_exp_date ---


def test_get_exp_date_none():
    """Test that None is returned when no date is provided."""
    assert get_exp_date({}) is None
    assert get_exp_date({"experiment_date": None}) is None


def test_get_exp_date_day_month_year():
    """Test parsing of dd.mm.YYYY format."""
    result = get_exp_date({"experiment_date": "27.03.2024"})
    assert result == datetime(2024, 3, 27)  # noqa: DTZ001


def test_get_exp_date_month_year():
    """Test parsing of 'Month, YYYY' format."""
    result = get_exp_date({"experiment_date": "November, 2024"})
    assert result == datetime(2024, 11, 1)  # noqa: DTZ001


def test_get_exp_date_unsupported_format():
    """Test that unsupported format raises."""
    with pytest.raises(ValueError, match="not supported"):
        get_exp_date({"experiment_date": "2024-03-27"})


def test_get_exp_date_invalid_string():
    """Test that invalid date string raises."""
    with pytest.raises(ValueError, match="not supported"):
        get_exp_date({"experiment_date": "not a date"})


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

    _check_required_contents(str(tmp_path), ["file_a.txt", "file_b.txt"], is_directory=True)


def test_check_required_contents_directory_missing(tmp_path):
    """Test that missing file in directory raises."""
    (tmp_path / "file_a.txt").write_text("a")

    with pytest.raises(ValueError, match="not found in"):
        _check_required_contents(str(tmp_path), ["file_a.txt", "missing.txt"], is_directory=True)


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


# --- _check_matrix_folder ---


def test_check_matrix_folder_valid(tmp_path):
    """Test that a valid matrix folder passes."""

    (tmp_path / "connectivity_matrix.h5").write_text("data")
    (tmp_path / "matrix_config.json").write_text(
        json_module.dumps({"pop1": {"single": {"path": "connectivity_matrix.h5"}}})
    )

    _check_matrix_folder(str(tmp_path))  # Should not raise


def test_check_matrix_folder_missing_config(tmp_path):
    """Test that missing matrix_config.json raises."""
    (tmp_path / "connectivity_matrix.h5").write_text("data")

    with pytest.raises(ValueError, match=r"matrix_config\.json missing"):
        _check_matrix_folder(str(tmp_path))


def test_check_matrix_folder_missing_referenced_file(tmp_path):
    """Test that a referenced matrix file not found raises."""

    (tmp_path / "matrix_config.json").write_text(
        json_module.dumps({"pop1": {"single": {"path": "missing.h5"}}})
    )

    with pytest.raises(ValueError, match="referenced in config but not found"):
        _check_matrix_folder(str(tmp_path))


def test_check_matrix_folder_nested_structure(tmp_path):
    """Test that a valid matrix folder with nested paths passes."""

    (tmp_path / "pop1" / "single").mkdir(parents=True)
    (tmp_path / "pop1" / "single" / "connectivity_matrix.h5").write_text("data")
    (tmp_path / "matrix_config.json").write_text(
        json_module.dumps({"pop1": {"single": {"path": "pop1/single/connectivity_matrix.h5"}}})
    )

    _check_matrix_folder(str(tmp_path))  # Should not raise


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
        get_parent_circuit(client, {"parent": "parent_circuit", "derivation_type": "invalid_type"})


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
        [role],  # find_role
    ]

    result = get_contributions(client, {"John Doe": {"type": "person", "role": "unspecified"}})
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


# --- register_derivation ---


def test_register_derivation_none_parent():
    """Test that None parent skips registration."""
    client = MagicMock()
    circuit = MagicMock()
    result = register_derivation(
        client=client,
        from_entity=None,
        derivation_type="circuit_extraction",
        registered_circuit=circuit,
        dry_run=False,
    )
    assert result is None
    client.register_entity.assert_not_called()


def test_register_derivation_invalid_type():
    """Test that None derivation type raises when parent is provided."""
    client = MagicMock()
    with pytest.raises(ValueError, match="derivation_type is required"):
        register_derivation(
            client=client,
            from_entity=MagicMock(),
            derivation_type=None,
            registered_circuit=MagicMock(),
            dry_run=False,
        )


def test_register_derivation_dry_run():
    """Test that dry_run skips registration."""
    client = MagicMock()
    result = register_derivation(
        client=client,
        from_entity=MagicMock(),
        derivation_type="circuit_extraction",
        registered_circuit=MagicMock(),
        dry_run=True,
    )
    assert result is None
    client.register_entity.assert_not_called()


def test_register_derivation_success():
    """Test successful derivation registration."""
    client = MagicMock()
    registered_derivation = MagicMock()
    client.register_entity.return_value = registered_derivation

    parent = MagicMock()
    circuit = MagicMock()

    with patch("obi_one.utils.circuit_registration.models.Derivation"):
        result = register_derivation(
            client=client,
            from_entity=parent,
            derivation_type="circuit_extraction",
            registered_circuit=circuit,
            dry_run=False,
        )
    assert result is registered_derivation
    client.register_entity.assert_called_once()


# --- register_contributions ---


def test_register_contributions_dry_run():
    """Test that dry_run skips registration."""
    client = MagicMock()
    circuit = MagicMock()
    contribution_dict = {"John Doe": {"agent": MagicMock(), "role": MagicMock()}}

    result = register_contributions(
        client=client,
        contribution_dict=contribution_dict,
        registered_circuit=circuit,
        dry_run=True,
    )
    assert result == []
    client.register_entity.assert_not_called()


def test_register_contributions_new():
    """Test that new contributions are registered."""
    client = MagicMock()
    circuit = MagicMock()
    registered_contr = MagicMock()
    client.register_entity.return_value = registered_contr
    # _contribution_exists returns None (not existing)
    client.search_entity.return_value.all.return_value = []

    agent = MagicMock(pref_label="John Doe", type="person")
    role = MagicMock()
    role.name = "unspecified"

    with patch("obi_one.utils.circuit_registration.models.Contribution"):
        result = register_contributions(
            client=client,
            contribution_dict={"John Doe": {"agent": agent, "role": role}},
            registered_circuit=circuit,
            dry_run=False,
        )
    assert len(result) == 1
    assert result[0] is registered_contr


def test_register_contributions_already_exists():
    """Test that existing contributions are skipped."""
    client = MagicMock()
    circuit = MagicMock(id="circuit-id")

    agent = MagicMock(pref_label="John Doe", type="person")
    role = MagicMock()
    role.name = "unspecified"

    # _contribution_exists finds a match
    existing = MagicMock()
    existing.agent.pref_label = "John Doe"
    existing.agent.type = "person"
    existing.role.name = "unspecified"

    # Mock: models.Contribution() returns a mock that matches the existing contribution
    mock_contr_model = MagicMock()
    mock_contr_model.entity.id = "circuit-id"
    mock_contr_model.agent.pref_label = "John Doe"
    mock_contr_model.agent.type = "person"
    mock_contr_model.role.name = "unspecified"

    with patch(
        "obi_one.utils.circuit_registration.models.Contribution",
        return_value=mock_contr_model,
    ):
        # search_entity for _contribution_exists returns the existing match
        client.search_entity.return_value.all.return_value = [existing]

        result = register_contributions(
            client=client,
            contribution_dict={"John Doe": {"agent": agent, "role": role}},
            registered_circuit=circuit,
            dry_run=False,
        )
    assert result == []
    client.register_entity.assert_not_called()


# --- register_publication_links ---


def test_register_publication_links_dry_run():
    """Test that dry_run skips registration."""
    client = MagicMock()
    circuit = MagicMock()
    publication_dict = {"10.1234/test": {"entity": MagicMock(), "type": "entity_source"}}

    result = register_publication_links(
        client=client,
        publication_dict=publication_dict,
        registered_circuit=circuit,
        dry_run=True,
    )
    assert result == []
    client.register_entity.assert_not_called()


def test_register_publication_links_new():
    """Test that new publication links are registered."""
    client = MagicMock()
    circuit = MagicMock(id="circuit-id")
    registered_link = MagicMock()
    client.register_entity.return_value = registered_link
    # No existing links found
    client.search_entity.return_value.all.return_value = []

    pub_entity = MagicMock(DOI="10.1234/test")

    with patch("obi_one.utils.circuit_registration.models.ScientificArtifactPublicationLink"):
        result = register_publication_links(
            client=client,
            publication_dict={"10.1234/test": {"entity": pub_entity, "type": "entity_source"}},
            registered_circuit=circuit,
            dry_run=False,
        )
    assert len(result) == 1
    assert result[0] is registered_link


def test_register_publication_links_already_exists():
    """Test that existing publication links are skipped."""
    client = MagicMock()
    circuit = MagicMock(id="circuit-id")
    # Existing link found
    client.search_entity.return_value.all.return_value = [MagicMock()]

    pub_entity = MagicMock(DOI="10.1234/test")

    with patch("obi_one.utils.circuit_registration.models.ScientificArtifactPublicationLink"):
        result = register_publication_links(
            client=client,
            publication_dict={"10.1234/test": {"entity": pub_entity, "type": "entity_source"}},
            registered_circuit=circuit,
            dry_run=False,
        )
    assert result == []
    client.register_entity.assert_not_called()


# --- register_asset ---


def test_register_asset_none_path():
    """Test that None file_path skips registration."""
    client = MagicMock()
    circuit = MagicMock()
    result = register_asset(
        client=client,
        file_path=None,
        asset_label="sonata_circuit",
        registered_circuit=circuit,
        dry_run=False,
    )
    assert result is None


def test_register_asset_unsupported_label():
    """Test that unsupported asset label raises."""
    client = MagicMock()
    circuit = MagicMock()
    with pytest.raises(ValueError, match="not supported"):
        register_asset(
            client=client,
            file_path="/some/path",
            asset_label="invalid_label",
            registered_circuit=circuit,
            dry_run=False,
        )


def test_register_asset_dry_run(tmp_path):
    """Test that dry_run skips registration after validation."""
    # Create a valid sonata_circuit directory
    (tmp_path / "circuit_config.json").write_text("{}")
    (tmp_path / "node_sets.json").write_text("{}")

    client = MagicMock()
    circuit = MagicMock()
    result = register_asset(
        client=client,
        file_path=str(tmp_path),
        asset_label="sonata_circuit",
        registered_circuit=circuit,
        dry_run=True,
    )
    assert result is None
    client.upload_directory.assert_not_called()


def test_register_asset_local_directory(tmp_path):
    """Test uploading a local directory asset."""
    # Create a valid sonata_circuit directory
    (tmp_path / "circuit_config.json").write_text("{}")
    (tmp_path / "node_sets.json").write_text("{}")

    client = MagicMock()
    uploaded_asset = MagicMock(id="asset-123")
    client.upload_directory.return_value = uploaded_asset
    circuit = MagicMock(id="circuit-id")

    result = register_asset(
        client=client,
        file_path=str(tmp_path),
        asset_label="sonata_circuit",
        registered_circuit=circuit,
        dry_run=False,
    )
    assert result is uploaded_asset
    client.upload_directory.assert_called_once()


def test_register_asset_local_file(tmp_path):
    """Test uploading a local file asset."""
    gz_file = tmp_path / "circuit.gz"
    gz_file.write_text("compressed data")

    client = MagicMock()
    uploaded_asset = MagicMock(id="asset-456")
    client.upload_file.return_value = uploaded_asset
    circuit = MagicMock(id="circuit-id")

    result = register_asset(
        client=client,
        file_path=str(gz_file),
        asset_label="compressed_sonata_circuit",
        registered_circuit=circuit,
        dry_run=False,
    )
    assert result is uploaded_asset
    client.upload_file.assert_called_once()


def test_register_asset_nonexistent_path():
    """Test that non-existent local path raises."""
    client = MagicMock()
    circuit = MagicMock()
    with pytest.raises(ValueError, match="does not exist"):
        register_asset(
            client=client,
            file_path="/nonexistent/path",
            asset_label="sonata_circuit",
            registered_circuit=circuit,
            dry_run=False,
        )


def test_register_asset_missing_required_contents(tmp_path):
    """Test that missing required contents raises."""
    # Create directory without required files
    (tmp_path / "some_file.txt").write_text("hello")

    client = MagicMock()
    circuit = MagicMock()
    with pytest.raises(ValueError, match="not found in"):
        register_asset(
            client=client,
            file_path=str(tmp_path),
            asset_label="sonata_circuit",
            registered_circuit=circuit,
            dry_run=False,
        )


@pytest.mark.parametrize(
    ("asset_label", "is_dir", "setup_fn"),
    [
        (
            "sonata_circuit",
            True,
            lambda p: [
                (p / "circuit_config.json").write_text("{}"),
                (p / "node_sets.json").write_text("{}"),
            ],
        ),
        ("compressed_sonata_circuit", False, lambda p: (p / "circuit.gz").write_text("data")),
        (
            "circuit_connectivity_matrices",
            True,
            lambda p: [
                (p / "matrix_config.json").write_text(json_module.dumps({})),
            ],
        ),
        (
            "circuit_visualization",
            False,
            lambda p: (p / "circuit_visualization.webp").write_text("img"),
        ),
        ("node_stats", False, lambda p: (p / "node_stats.webp").write_text("img")),
        ("network_stats_a", False, lambda p: (p / "network_stats_a.webp").write_text("img")),
        ("network_stats_b", False, lambda p: (p / "network_stats_b.webp").write_text("img")),
        (
            "simulation_designer_image",
            False,
            lambda p: (p / "simulation_designer_image.png").write_text("img"),
        ),
    ],
)
def test_register_asset_all_labels(tmp_path, asset_label, is_dir, setup_fn):
    """Test that all supported asset labels can be registered."""
    if is_dir:
        asset_path = tmp_path / asset_label
        asset_path.mkdir()
        setup_fn(asset_path)
        file_path = str(asset_path)
    else:
        setup_fn(tmp_path)
        # For files, find the created file
        files = [f for f in tmp_path.iterdir() if f.is_file()]
        file_path = str(files[0])

    client = MagicMock()
    uploaded = MagicMock(id=f"{asset_label}-id")
    client.upload_directory.return_value = uploaded
    client.upload_file.return_value = uploaded
    circuit = MagicMock(id="circuit-id")

    result = register_asset(
        client=client,
        file_path=file_path,
        asset_label=asset_label,
        registered_circuit=circuit,
        dry_run=False,
    )
    assert result is uploaded
    if is_dir:
        client.upload_directory.assert_called_once()
    else:
        client.upload_file.assert_called_once()


# --- register_circuit ---


class _FakeCircuit:
    """Fake Circuit class that accepts any kwargs and supports isinstance."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_patch_models_circuit = patch("obi_one.utils.circuit_registration.models.Circuit", _FakeCircuit)


def test_register_circuit_dry_run():
    """Test that dry_run computes properties but does not register."""
    circuit_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
    client = MagicMock()

    with _patch_models_circuit:
        result = register_circuit(
            client=client,
            circuit_path=str(circuit_path),
            name="test_circuit",
            description="A test circuit",
            build_category="computational_model",
            brain_region=MagicMock(),
            subject=MagicMock(),
            skip_additional_assets=True,
            dry_run=True,
        )

    assert result is None
    client.register_entity.assert_not_called()


def test_register_circuit_registers_entity():
    """Test that register_circuit registers the entity and returns it."""
    circuit_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
    client = MagicMock()
    registered = MagicMock()
    registered.name = "test_circuit"
    registered.id = "new-id"
    client.register_entity.return_value = registered

    with (
        _patch_models_circuit,
        patch("obi_one.utils.circuit_registration.register_asset"),
        patch("obi_one.utils.circuit_registration.generate_additional_circuit_assets"),
    ):
        result = register_circuit(
            client=client,
            circuit_path=str(circuit_path),
            name="test_circuit",
            description="A test circuit",
            build_category="computational_model",
            brain_region=MagicMock(),
            subject=MagicMock(),
            dry_run=False,
        )

    assert result is registered
    client.register_entity.assert_called_once()


def test_register_circuit_with_derivation():
    """Test that derivation link is created when parent is provided."""
    circuit_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
    client = MagicMock()
    registered = MagicMock()
    registered.name = "test_circuit"
    registered.id = "new-id"
    client.register_entity.return_value = registered
    parent = MagicMock()

    with (
        _patch_models_circuit,
        patch("obi_one.utils.circuit_registration.register_asset"),
        patch("obi_one.utils.circuit_registration.register_derivation") as mock_derivation,
        patch("obi_one.utils.circuit_registration.generate_additional_circuit_assets"),
    ):
        register_circuit(
            client=client,
            circuit_path=str(circuit_path),
            name="test_circuit",
            description="A test circuit",
            build_category="computational_model",
            brain_region=MagicMock(),
            subject=MagicMock(),
            parent=parent,
            derivation_type="circuit_extraction",
            dry_run=False,
        )

    mock_derivation.assert_called_once()


def test_register_circuit_skip_additional_assets():
    """Test that skip_additional_assets prevents asset generation."""
    circuit_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
    client = MagicMock()
    registered = MagicMock()
    registered.name = "test_circuit"
    registered.id = "new-id"
    client.register_entity.return_value = registered

    with (
        _patch_models_circuit,
        patch("obi_one.utils.circuit_registration.register_asset"),
        patch("obi_one.utils.circuit_registration.generate_additional_circuit_assets") as mock_gen,
    ):
        register_circuit(
            client=client,
            circuit_path=str(circuit_path),
            name="test_circuit",
            description="A test circuit",
            build_category="computational_model",
            brain_region=MagicMock(),
            subject=MagicMock(),
            skip_additional_assets=True,
            dry_run=False,
        )

    mock_gen.assert_not_called()


def test_register_circuit_invalid_path():
    """Test that non-existent circuit path raises."""
    client = MagicMock()
    with pytest.raises(ValueError, match="Circuit config not found"):
        register_circuit(
            client=client,
            circuit_path="/nonexistent/path",
            name="test",
            description="test",
            build_category="computational_model",
            brain_region=MagicMock(),
            subject=MagicMock(),
        )
