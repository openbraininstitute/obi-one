"""Cost estimation helpers for circuit simplification tasks."""

import json
import tempfile
from pathlib import Path
from uuid import UUID

from entitysdk import models
from entitysdk.client import Client
from entitysdk.types import AssetLabel

from obi_one import deserialize_obi_object_from_json_data
from obi_one.db_sdk import db_sdk
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.task import CircuitSimplificationSingleConfig


def estimate_circuit_simplification_count(*, db_client: Client, config_id: UUID) -> int:
    """Estimate accounting count for circuit simplification.

    The estimate uses the number of neurons in the target neuron set.
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

    single_config = CircuitSimplificationSingleConfig.model_validate(
        deserialize_obi_object_from_json_data(config_dict).model_dump()
    )

    parent_circuit = single_config.initialize.circuit
    target_neuron_set_ref = single_config.initialize.target_neuron_set
    if target_neuron_set_ref is None:
        target_neuron_set_ref = single_config.default_neuron_set_reference

    if isinstance(parent_circuit, CircuitFromID):
        with tempfile.TemporaryDirectory() as temp_dir:
            staged_circuit = parent_circuit.stage_circuit(
                db_client=db_client,
                dest_dir=Path(temp_dir) / "sonata_circuit",
                entity_cache=False,
            )
            neuron_ids = target_neuron_set_ref.block.get_neuron_ids(  # ty:ignore[unresolved-attribute]
                circuit=staged_circuit
            )
    else:
        neuron_ids = target_neuron_set_ref.block.get_neuron_ids(  # ty:ignore[unresolved-attribute]
            circuit=parent_circuit  # ty:ignore[invalid-argument-type]
        )

    neuron_count = sum(len(v) for v in neuron_ids.values())
    if neuron_count == 0:
        msg = "Circuit simplification target neuron set resolved to 0 neurons."
        raise ValueError(msg)
    return neuron_count
