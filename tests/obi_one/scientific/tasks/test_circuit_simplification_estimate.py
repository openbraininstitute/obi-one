from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from obi_one.scientific.tasks.circuit_simplification.estimate import (
    estimate_circuit_simplification_count,
)


def test_estimate_circuit_simplification_count_from_target_neuron_set_size():
    db_client = MagicMock()
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace()
    fake_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: {"pop_a": [101, 202], "pop_b": [303]}
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit,
            target_neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
        default_neuron_set_reference=SimpleNamespace(block=fake_neuron_set),
    )
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitSimplificationSingleConfig"}
    )
    db_client.get_entity.return_value = task_config

    with (
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.db_sdk.get_task_config_asset_content",
            return_value={"type": "CircuitSimplificationSingleConfig"},
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.CircuitSimplificationSingleConfig.model_validate",
            return_value=fake_config,
        ),
    ):
        assert estimate_circuit_simplification_count(db_client=db_client, config_id=config_id) == 3


def test_estimate_circuit_simplification_count_uses_default_neuron_set():
    db_client = MagicMock()
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace()
    default_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: {"pop_a": [1, 2]},
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit,
            target_neuron_set=None,
        ),
        default_neuron_set_reference=SimpleNamespace(block=default_neuron_set),
    )
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitSimplificationSingleConfig"}
    )
    db_client.get_entity.return_value = task_config

    with (
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.db_sdk.get_task_config_asset_content",
            return_value={"type": "CircuitSimplificationSingleConfig"},
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.CircuitSimplificationSingleConfig.model_validate",
            return_value=fake_config,
        ),
    ):
        assert estimate_circuit_simplification_count(db_client=db_client, config_id=config_id) == 2


def test_estimate_circuit_simplification_count_raises_for_empty_set():
    db_client = MagicMock()
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace()
    fake_neuron_set = SimpleNamespace(get_neuron_ids=lambda **_kwargs: {})
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit,
            target_neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
        default_neuron_set_reference=SimpleNamespace(block=fake_neuron_set),
    )
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitSimplificationSingleConfig"}
    )
    db_client.get_entity.return_value = task_config

    with (
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.db_sdk.get_task_config_asset_content",
            return_value={"type": "CircuitSimplificationSingleConfig"},
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.CircuitSimplificationSingleConfig.model_validate",
            return_value=fake_config,
        ),
        pytest.raises(ValueError, match="resolved to 0 neurons"),
    ):
        estimate_circuit_simplification_count(db_client=db_client, config_id=config_id)


def test_estimate_circuit_simplification_count_with_circuit_from_id_staging():
    db_client = MagicMock()
    config_id = uuid4()
    task_config = SimpleNamespace()
    staged_circuit = SimpleNamespace()
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitSimplificationSingleConfig"}
    )

    class FakeCircuitFromID:
        def stage_circuit(self, **_kwargs):
            return staged_circuit

    fake_circuit_from_id = FakeCircuitFromID()
    fake_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: {"pop_a": [1], "pop_b": [2]},
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit_from_id,
            target_neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
        default_neuron_set_reference=SimpleNamespace(block=fake_neuron_set),
    )
    db_client.get_entity.return_value = task_config

    with (
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.db_sdk.get_task_config_asset_content",
            return_value={"type": "CircuitSimplificationSingleConfig"},
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.deserialize_obi_object_from_json_data",
            return_value=fake_deserialized,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.CircuitSimplificationSingleConfig.model_validate",
            return_value=fake_config,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.estimate.CircuitFromID",
            FakeCircuitFromID,
        ),
    ):
        assert estimate_circuit_simplification_count(db_client=db_client, config_id=config_id) == 2
