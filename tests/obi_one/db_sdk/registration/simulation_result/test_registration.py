from unittest.mock import MagicMock
from uuid import UUID

import pytest

from obi_one.db_sdk.registration.simulation_result import register as test_module


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def simulation_id():
    return UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def spike_report_file(tmp_path):
    path = tmp_path / "spikes.h5"
    path.write_text("spike data")
    return path


@pytest.fixture
def voltage_report_files(tmp_path):
    voltage_report_file_nwb = tmp_path / "voltage.nwb"
    voltage_report_file_nwb.write_text("voltage nwb")
    voltage_report_file_h5 = tmp_path / "voltage.h5"
    voltage_report_file_h5.write_text("voltage h5")
    return [voltage_report_file_nwb, voltage_report_file_h5]


def test_register_simulation_results_registers_entity_and_uploads_files(
    mock_client, simulation_id, spike_report_file, voltage_report_files
):
    simulation_result = MagicMock()
    simulation_result.id = "result-123"
    mock_client.register_entity.return_value = simulation_result

    returned = test_module.register_simulation_results(
        client=mock_client,
        simulation_id=simulation_id,
        spike_report_file=spike_report_file,
        voltage_report_files=voltage_report_files,
        name="Simulation result",
        description="Simulation result",
    )

    mock_client.register_entity.assert_called_once()
    call_args, _ = mock_client.register_entity.call_args
    assert len(call_args) == 1
    entity_arg = call_args[0]
    assert entity_arg.simulation_id == simulation_id

    assert returned == simulation_result

    mock_client.upload_file.assert_any_call(
        entity_id=simulation_result.id,
        entity_type=type(simulation_result),
        file_path=spike_report_file,
        file_content_type=test_module.ContentType.application_x_hdf5,
        asset_label=test_module.AssetLabel.spike_report,
    )

    for path in voltage_report_files:
        expected_content_type = test_module.EXTENSION_TO_CONTENT_TYPE[path.suffix]
        mock_client.upload_file.assert_any_call(
            entity_id=simulation_result.id,
            entity_type=type(simulation_result),
            file_path=path,
            file_content_type=expected_content_type,
            asset_label=test_module.AssetLabel.voltage_report,
        )


def test_register_simulation_results_passes_through_name_and_description(
    mock_client, simulation_id, spike_report_file
):
    """Each backend supplies its own name and description; there is no default."""
    mock_client.register_entity.return_value = MagicMock(id="result-123")

    test_module.register_simulation_results(
        client=mock_client,
        simulation_id=simulation_id,
        spike_report_file=spike_report_file,
        voltage_report_files=[],
        name="custom name",
        description="custom description",
    )

    entity_arg = mock_client.register_entity.call_args[0][0]
    assert (entity_arg.name, entity_arg.description) == ("custom name", "custom description")
