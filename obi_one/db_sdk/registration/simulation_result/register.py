"""Registration of simulation results in entitycore."""

import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from entitysdk import Client, models
from entitysdk.types import AssetLabel, ContentType

L = logging.getLogger(__name__)


EXTENSION_TO_CONTENT_TYPE = {
    ".nwb": ContentType.application_nwb,
    ".h5": ContentType.application_x_hdf5,
}


def _upload_report(
    *,
    client: Client,
    simulation_result: models.SimulationResult,
    file_path: Path,
    file_content_type: ContentType,
    asset_label: AssetLabel,
) -> None:
    """Upload a single report file as an asset on the simulation result."""
    L.info(
        "SimulationResult: Uploading Asset(path=%s, content_type=%s, label=%s)",
        file_path,
        file_content_type,
        asset_label,
    )
    asset = client.upload_file(
        entity_id=simulation_result.id,
        entity_type=type(simulation_result),
        file_path=file_path,
        file_content_type=file_content_type,
        asset_label=asset_label,
    )
    L.info("SimulationResult: Attached Asset(id=%s)", asset.id)


def register_simulation_results(
    *,
    client: Client,
    simulation_id: UUID,
    spike_report_file: Path,
    voltage_report_files: Sequence[Path],
    name: str,
    description: str,
) -> models.SimulationResult:
    """Register a SimulationResult and attach its spike and voltage report assets.

    Args:
        client: The entitycore SDK client.
        simulation_id: ID of the simulation these results belong to.
        spike_report_file: Path to the spike report (HDF5).
        voltage_report_files: Paths to the voltage reports. The content type of each is
            derived from its extension via EXTENSION_TO_CONTENT_TYPE.
        name: Name for the registered entity.
        description: Description for the registered entity.

    Returns:
        The registered SimulationResult entity.
    """
    simulation_result = client.register_entity(
        models.SimulationResult(
            name=name,
            description=description,
            simulation_id=simulation_id,
        )
    )
    L.info(f"SimulationResult: Registered entity {simulation_result.id}")

    _upload_report(
        client=client,
        simulation_result=simulation_result,
        file_path=spike_report_file,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.spike_report,
    )

    for path in voltage_report_files:
        _upload_report(
            client=client,
            simulation_result=simulation_result,
            file_path=path,
            file_content_type=EXTENSION_TO_CONTENT_TYPE[path.suffix],
            asset_label=AssetLabel.voltage_report,
        )

    return simulation_result
