import logging

from entitysdk import Client, models
from entitysdk.types import AssetLabel, ContentType

from obi_one.scientific.library.simulation.schemas import SimulationMetadata, SimulationResults

L = logging.getLogger(__name__)


EXTENSION_TO_CONTENT_TYPE = {
    ".nwb": ContentType.application_nwb,
    ".h5": ContentType.application_x_hdf5,
}


def register_simulation_results(
    *,
    client: Client,
    simulation_metadata: SimulationMetadata,
    simulation_results: SimulationResults,
) -> None:
    # TODO: Add proper name, consider adding a description
    simulation_result = client.register_entity(
        models.SimulationResult(
            name="simulation_result",
            description="Simulation result",
            simulation_id=simulation_metadata.simulation_id,
        )
    )
    L.info(f"SimulationResult: Registered entity {simulation_result.id}")

    asset = client.upload_file(
        entity_id=simulation_result.id,  # ty:ignore[invalid-argument-type]
        entity_type=type(simulation_result),
        file_path=simulation_results.spike_report_file,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.spike_report,
    )
    L.info(
        "SimulationResult: Attached Asset(id=%s, path=%s, content_type=%s, label=%s)",
        asset.id,
        asset.path,
        asset.content_type,
        asset.label,
    )

    for path in simulation_results.voltage_report_files:
        asset = client.upload_file(
            entity_id=simulation_result.id,  # ty:ignore[invalid-argument-type]
            entity_type=type(simulation_result),
            file_path=path,
            file_content_type=EXTENSION_TO_CONTENT_TYPE[path.suffix],
            asset_label=AssetLabel.voltage_report,
        )
        L.info(
            "SimulationResult: Attached Asset(id=%s, path=%s, content_type=%s, label=%s)",
            asset.id,
            asset.path,
            asset.content_type,
            asset.label,
        )

    return simulation_result  # ty:ignore[invalid-return-type]
