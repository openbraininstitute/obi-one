import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import entitysdk
import numpy as np

from obi_one.scientific.tasks.circuit_extraction.estimate import estimate_circuit_extraction_count


def test_estimate_circuit_extraction_count_from_neuron_set_size():
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # noqa: S106
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace(default_population_name="default_pop")
    fake_neuron_set = SimpleNamespace(get_neuron_ids=lambda **_kwargs: np.array([101, 202, 303]))
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(circuit=fake_circuit),
        neuron_set=fake_neuron_set,
    )
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitExtractionSingleConfig"}
    )

    db_client.get_entity = lambda **_kwargs: task_config
    db_client.download_content = lambda **_kwargs: json.dumps({}).encode("utf-8")

    with (
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.db_sdk.get_entity_asset_by_label",
            return_value=SimpleNamespace(id=uuid4()),
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.CircuitExtractionSingleConfig.model_validate",
            return_value=fake_config,
        ),
    ):
        assert estimate_circuit_extraction_count(db_client=db_client, config_id=config_id) == 3


def test_estimate_circuit_extraction_count_has_minimum_one_for_empty_set():
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # noqa: S106
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace(default_population_name="default_pop")
    fake_neuron_set = SimpleNamespace(get_neuron_ids=lambda **_kwargs: np.array([]))
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(circuit=fake_circuit),
        neuron_set=fake_neuron_set,
    )
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitExtractionSingleConfig"}
    )

    db_client.get_entity = lambda **_kwargs: task_config
    db_client.download_content = lambda **_kwargs: json.dumps({}).encode("utf-8")

    with (
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.db_sdk.get_entity_asset_by_label",
            return_value=SimpleNamespace(id=uuid4()),
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.CircuitExtractionSingleConfig.model_validate",
            return_value=fake_config,
        ),
    ):
        assert estimate_circuit_extraction_count(db_client=db_client, config_id=config_id) == 1


def test_estimate_circuit_extraction_count_with_circuit_from_id_staging():
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # noqa: S106
    config_id = uuid4()
    task_config = SimpleNamespace()
    staged_circuit = SimpleNamespace(default_population_name="default_pop")
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitExtractionSingleConfig"}
    )

    class FakeCircuitFromID:
        def stage_circuit(self, **_kwargs):
            return staged_circuit

    fake_circuit_from_id = FakeCircuitFromID()
    fake_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: np.array([1, 2]),
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(circuit=fake_circuit_from_id),
        neuron_set=fake_neuron_set,
    )

    db_client.get_entity = lambda **_kwargs: task_config
    db_client.download_content = lambda **_kwargs: json.dumps({}).encode("utf-8")

    with (
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.db_sdk.get_entity_asset_by_label",
            return_value=SimpleNamespace(id=uuid4()),
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.CircuitExtractionSingleConfig.model_validate",
            return_value=fake_config,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.CircuitFromID",
            FakeCircuitFromID,
        ),
    ):
        assert estimate_circuit_extraction_count(db_client=db_client, config_id=config_id) == 2
