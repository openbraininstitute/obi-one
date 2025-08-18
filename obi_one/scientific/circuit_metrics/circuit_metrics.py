import json
import tempfile
from pathlib import Path
from typing import Any

from entitysdk.client import Client
from entitysdk.models.circuit import Circuit
from pydantic import BaseModel


class CircuitMetricsOutput(BaseModel):
    config: dict[str, Any]


def get_circuit_metrics(
    circuit_id: str,
    db_client: Client,
) -> CircuitMetricsOutput:
    circuit = db_client.get_entity(
        entity_id=circuit_id,
        entity_type=Circuit,
    )
    directory_assets = [
        a for a in circuit.assets if a.is_directory and a.label.value == "sonata_circuit"
    ]
    if len(directory_assets) != 1:
        error_msg = "Circuit must have exactly one directory asset."
        raise ValueError(error_msg)

    asset_id = directory_assets[0].id

    # db_client.download_content does not support `asset_path` at the time of writing this
    # Use db_client.download_file with temporary directory instead
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = Path(temp_dir) / "circuit_config.json"

        db_client.download_file(
            entity_id=circuit_id,
            entity_type=Circuit,
            asset_id=asset_id,
            output_path=temp_file_path,
            asset_path="circuit_config.json",
        )

        # Read the file and load JSON
        content = Path(temp_file_path).read_text(encoding="utf-8")
        config_dict = json.loads(content)

    return CircuitMetricsOutput(config=config_dict)
