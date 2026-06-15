"""Tests for obi_one.utils.circuit_customization.upload."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from freezegun import freeze_time

from obi_one.utils.circuit_customization.upload import upload_customized_circuit
from obi_one.utils.circuit_registration.links import CustomizationType


@pytest.fixture
def mock_parent_circuit():
    circuit = MagicMock()
    circuit.name = "parent_circuit"
    circuit.id = uuid4()
    circuit.brain_region = MagicMock()
    circuit.subject = MagicMock()
    circuit.build_category = "computational_model"
    circuit.target_simulator = "NEURON"
    circuit.license = MagicMock()
    circuit.atlas_id = uuid4()
    circuit.root_circuit_id = None
    return circuit


@pytest.fixture
def mock_client(mock_parent_circuit):
    client = MagicMock()
    client.get_entity.return_value = mock_parent_circuit
    return client


# --- UUID resolution ---


def test_upload_resolves_uuid(mock_client, mock_parent_circuit):
    """Test that a UUID is resolved to a circuit entity."""
    circuit_id = mock_parent_circuit.id
    mock_client.get_entity.return_value = mock_parent_circuit

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=circuit_id,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    # First get_entity call should be to resolve the UUID to a Circuit
    first_call = mock_client.get_entity.call_args_list[0]
    assert first_call.kwargs["entity_id"] == circuit_id


def test_upload_accepts_circuit_entity(mock_client, mock_parent_circuit):
    """Test that a circuit entity is used directly without resolving."""
    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.emodel_addition,
            dry_run=True,
        )

    mock_register.assert_called_once()


# --- brain_region and subject validation ---


def test_upload_raises_if_no_brain_region(mock_client, mock_parent_circuit):
    """Test that missing brain_region raises ValueError."""
    mock_parent_circuit.brain_region = None

    with pytest.raises(ValueError, match="no brain_region set and none provided"):
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
        )


def test_upload_raises_if_no_subject(mock_client, mock_parent_circuit):
    """Test that missing subject raises ValueError."""
    mock_parent_circuit.subject = None

    with pytest.raises(ValueError, match="no subject set and none provided"):
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
        )


# --- overrides ---


def test_upload_brain_region_override(mock_client, mock_parent_circuit):
    """Test that brain_region_override takes precedence over parent's."""
    mock_parent_circuit.brain_region = None
    override_br = MagicMock()

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            brain_region_override=override_br,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["brain_region"] is override_br


def test_upload_subject_override(mock_client, mock_parent_circuit):
    """Test that subject_override takes precedence over parent's."""
    mock_parent_circuit.subject = None
    override_subj = MagicMock()

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.emodel_modification,
            subject_override=override_subj,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["subject"] is override_subj


# --- description prefix ---


def test_upload_description_prefix(mock_client, mock_parent_circuit):
    """Test that description is prefixed with the parent circuit name."""
    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="modified synapses",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    expected = f"Customization of circuit '{mock_parent_circuit.name}': modified synapses"
    assert call_kwargs["description"] == expected


# --- derivation parameters ---


def test_upload_passes_derivation_type_and_label(mock_client, mock_parent_circuit):
    """Test that derivation_type and derivation_label are passed correctly."""
    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.population_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["derivation_type"] == "circuit_customization"
    assert call_kwargs["derivation_label"] == "population_modification"


# --- atlas resolution ---


def test_upload_resolves_atlas(mock_client, mock_parent_circuit):
    """Test that atlas is resolved from parent's atlas_id."""
    mock_atlas = MagicMock()
    mock_client.get_entity.return_value = mock_atlas

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        # Need to pass entity directly since get_entity is mocked for atlas too
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["atlas"] is mock_atlas


def test_upload_no_atlas_when_parent_has_none(mock_client, mock_parent_circuit):
    """Test that atlas is None when parent has no atlas_id."""
    mock_parent_circuit.atlas_id = None

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["atlas"] is None


# --- root circuit resolution ---


def test_upload_root_is_parent_id_when_no_root(mock_client, mock_parent_circuit):
    """Test that root defaults to parent's id when root_circuit_id is None."""
    mock_parent_circuit.root_circuit_id = None

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["root"] == mock_parent_circuit.id


def test_upload_root_is_parent_root_circuit_id(mock_client, mock_parent_circuit):
    """Test that root uses parent's root_circuit_id when available."""
    root_id = uuid4()
    mock_parent_circuit.root_circuit_id = root_id

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["root"] == root_id


# --- experiment_date ---


@freeze_time("2026-06-12 10:00:00")
def test_upload_experiment_date_is_current(mock_client, mock_parent_circuit):
    """Test that experiment_date is set to the current UTC time."""
    from datetime import UTC, datetime

    with patch("obi_one.utils.circuit_customization.upload.register_circuit") as mock_register:
        mock_register.return_value = None
        upload_customized_circuit(
            client=mock_client,
            name="custom",
            description="test",
            circuit_path="/tmp/circuit",
            customized_from=mock_parent_circuit,
            customization_type=CustomizationType.synaptic_modification,
            dry_run=True,
        )

    call_kwargs = mock_register.call_args.kwargs
    assert call_kwargs["experiment_date"] == datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)
