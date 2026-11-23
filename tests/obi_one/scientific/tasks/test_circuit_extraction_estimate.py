import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import entitysdk
import pytest

from obi_one.core.info import Info
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.circuit_extraction.config import CircuitExtractionSingleConfig
from obi_one.scientific.tasks.circuit_extraction.estimate import estimate_circuit_extraction_count

from tests.utils import CIRCUIT_DIR


def test_estimate_circuit_extraction_count_from_neuron_set_size():
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # ruff: ignore[hardcoded-password-func-arg]
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace()
    fake_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: {"pop_a": [101, 202], "pop_b": [303]}
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit,
            neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
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


def test_estimate_circuit_extraction_count_raises_for_empty_set():
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # ruff: ignore[hardcoded-password-func-arg]
    config_id = uuid4()
    task_config = SimpleNamespace()
    fake_circuit = SimpleNamespace()
    fake_neuron_set = SimpleNamespace(get_neuron_ids=lambda **_kwargs: {})
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit,
            neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
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
        pytest.raises(ValueError, match="resolved to 0 neurons"),
    ):
        estimate_circuit_extraction_count(db_client=db_client, config_id=config_id)


def test_estimate_circuit_extraction_count_with_circuit_from_id_staging():
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # ruff: ignore[hardcoded-password-func-arg]
    config_id = uuid4()
    task_config = SimpleNamespace()
    staged_circuit = SimpleNamespace()
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitExtractionSingleConfig"}
    )

    class FakeCircuitFromID:
        def __init__(self):
            self.stage_calls = []

        def stage_circuit(self, **kwargs):
            self.stage_calls.append(kwargs)
            return staged_circuit

    fake_circuit_from_id = FakeCircuitFromID()
    fake_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: {"pop_a": [1], "pop_b": [2]},
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit_from_id,
            neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
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

    # Only the node files are staged (counting neurons never reads edges/morphologies), so the
    # whole circuit is never downloaded.
    assert len(fake_circuit_from_id.stage_calls) == 1
    assert fake_circuit_from_id.stage_calls[0]["nodes_only"] is True


def test_estimate_circuit_extraction_count_stages_nodes_only():
    """Staging always requests nodes_only=True; the full circuit is never downloaded."""
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # ruff: ignore[hardcoded-password-func-arg]
    config_id = uuid4()
    task_config = SimpleNamespace()
    staged_circuit = SimpleNamespace()
    fake_deserialized = SimpleNamespace(
        model_dump=lambda: {"type": "CircuitExtractionSingleConfig"}
    )

    stage_calls = []

    class FakeCircuitFromID:
        id_str = "circuit-id"

        def stage_circuit(self, **kwargs):
            stage_calls.append(kwargs)
            # Full circuit staging (nodes_only=False) must never be requested: it would try to
            # download edges/morphologies and can exhaust the small tmpfs.
            if not kwargs.get("nodes_only"):
                msg = "full staging must not be used by the count estimator"
                raise AssertionError(msg)
            return staged_circuit

    fake_circuit_from_id = FakeCircuitFromID()
    fake_neuron_set = SimpleNamespace(
        get_neuron_ids=lambda **_kwargs: {"pop_a": [1, 2, 3]},
    )
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(
            circuit=fake_circuit_from_id,
            neuron_set=SimpleNamespace(block=fake_neuron_set),
        ),
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
        assert estimate_circuit_extraction_count(db_client=db_client, config_id=config_id) == 3

    # Exactly one staging attempt, and it is nodes_only.
    assert len(stage_calls) == 1
    assert stage_calls[0]["nodes_only"] is True


def _run_estimate_with_config(single_config):
    db_client = entitysdk.Client(api_url="http://my-url", token_manager="token")  # ruff: ignore[hardcoded-password-func-arg]
    db_client.get_entity = lambda **_kwargs: SimpleNamespace()
    db_client.download_content = lambda **_kwargs: json.dumps({}).encode("utf-8")
    with (
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.db_sdk.get_entity_asset_by_label",
            return_value=SimpleNamespace(id=uuid4()),
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.deserialize_obi_object_from_json_data",
            return_value=SimpleNamespace(model_dump=dict),
        ),
        patch(
            "obi_one.scientific.tasks.circuit_extraction.estimate.CircuitExtractionSingleConfig.model_validate",
            return_value=single_config,
        ),
    ):
        return estimate_circuit_extraction_count(db_client=db_client, config_id=uuid4())


def test_estimate_circuit_extraction_count_uses_default_neuron_set():
    """Without a neuron set, the default one is counted, as the task extracts it."""
    default_neuron_set = SimpleNamespace(get_neuron_ids=lambda **_kwargs: {"pop_a": [1, 2]})
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(circuit=SimpleNamespace(), neuron_set=None),
        default_neuron_set_reference=SimpleNamespace(block=default_neuron_set),
    )
    assert _run_estimate_with_config(fake_config) == 2


def test_estimate_circuit_extraction_count_default_neuron_set_counts_biophysical_neurons():
    """The default neuron set of a real config counts the biophysical neurons only."""
    config = CircuitExtractionSingleConfig.empty_config()
    config.set(Info(campaign_name="test", campaign_description="test"), name="info")
    circuit = Circuit(
        name="N_10__top_nodes_dim6",
        path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
    )
    config.set(CircuitExtractionSingleConfig.Initialize(circuit=circuit), name="initialize")
    assert config.initialize.neuron_set is None
    # 10 biophysical neurons; the 351 virtual ones (POm, VPM) are not counted
    assert _run_estimate_with_config(config) == 10
