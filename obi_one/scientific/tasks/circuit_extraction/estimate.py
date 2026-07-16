"""Cost estimation helpers for circuit extraction tasks."""

import json
import tempfile
from pathlib import Path
from uuid import UUID

from entitysdk import models
from entitysdk.client import Client
from entitysdk.types import AssetLabel

from obi_one import deserialize_obi_object_from_json_data
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_extraction.task import CircuitExtractionSingleConfig
from obi_one.utils import db_sdk


def estimate_circuit_extraction_count(*, db_client: Client, config_id: UUID) -> int:
    """Estimate accounting count for circuit extraction.

    The estimate uses the number of neurons in the extraction neuron set.
    """
    task_config = db_client.get_entity(entity_id=config_id, entity_type=models.TaskConfig)
    config_asset = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=task_config,
        asset_label=AssetLabel.task_config,
    )
    config_bytes = db_client.download_content(
        entity_id=config_id,
        entity_type=models.TaskConfig,
        asset_id=config_asset.id,
    )
    config_dict = json.loads(config_bytes.decode("utf-8"))

    single_config = CircuitExtractionSingleConfig.model_validate(
        deserialize_obi_object_from_json_data(config_dict).model_dump()
    )

    parent_circuit = single_config.initialize.circuit
    if isinstance(parent_circuit, CircuitFromID):
        with tempfile.TemporaryDirectory() as temp_dir:
            staged_circuit = parent_circuit.stage_circuit(
                db_client=db_client,
                dest_dir=Path(temp_dir) / "sonata_circuit",
                entity_cache=False,
            )
            neuron_ids = single_config.neuron_set.get_neuron_ids(circuit=staged_circuit)
    else:
        neuron_ids = single_config.neuron_set.get_neuron_ids(circuit=parent_circuit)  # ty:ignore[invalid-argument-type]

    neuron_count = sum(len(v) for v in neuron_ids.values())
    if neuron_count == 0:
        msg = "Circuit extraction neuron set resolved to 0 neurons."
        raise ValueError(msg)
    return neuron_count
