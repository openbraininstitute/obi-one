from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from entitysdk import models
from entitysdk.types import CircuitScale, EntityType

from app.endpoints import circuit_helpers as test_module
from app.errors import ApiError
from app.schemas.task import AfterSuccess

BUILT = [
    SimpleNamespace(label=label)
    for label in ("compressed_sonata_circuit", "circuit_connectivity_matrices")
]


def after_success(generated, circuits):
    by_id = {circuit.id: circuit for circuit in circuits}
    return AfterSuccess(
        activity=SimpleNamespace(id=uuid4(), generated=generated),
        db_client=Mock(get_entity=Mock(side_effect=lambda entity_id, **_: by_id[entity_id])),
        ls_client=Mock(),
        compute_cell="cell_a",
        project_id=uuid4(),
        virtual_lab_id=uuid4(),
    )


def test_build_missing_circuit_assets():
    circuits = [
        SimpleNamespace(id=uuid4(), scale=CircuitScale.small, assets=BUILT),
        SimpleNamespace(id=uuid4(), scale=CircuitScale.single, assets=BUILT),
        SimpleNamespace(id=uuid4(), scale=CircuitScale.whole_brain, assets=[]),
    ]
    generated = [
        SimpleNamespace(id=circuits[0].id, type=EntityType.circuit),
        SimpleNamespace(id=uuid4(), type=EntityType.simulation),
        SimpleNamespace(id=circuits[1].id, type=EntityType.circuit),
        SimpleNamespace(id=circuits[2].id, type=EntityType.circuit),
    ]
    done = after_success(generated, circuits)

    with patch.object(
        test_module, "trigger_asset_generation_task", return_value=uuid4()
    ) as trigger:
        test_module.build_missing_circuit_assets(done)

    assert [call.kwargs["entity_id"] for call in done.db_client.get_entity.call_args_list] == [
        circuit.id for circuit in circuits
    ]
    assert {call.kwargs["entity_type"] for call in done.db_client.get_entity.call_args_list} == {
        models.Circuit
    }
    assert [
        (call.kwargs["circuit_id"], call.kwargs["scale"]) for call in trigger.call_args_list
    ] == [(circuit.id, circuit.scale) for circuit in (circuits[0], circuits[2])]
    for call in trigger.call_args_list:
        assert call.kwargs["ls_client"] is done.ls_client
        assert call.kwargs["compute_cell"] == "cell_a"
        assert call.kwargs["project_id"] == done.project_id
        assert call.kwargs["virtual_lab_id"] == done.virtual_lab_id


@pytest.mark.parametrize("generated", [None, []])
def test_build_missing_circuit_assets_of_an_activity_that_generated_nothing(generated):
    with patch.object(test_module, "trigger_asset_generation_task") as trigger:
        test_module.build_missing_circuit_assets(after_success(generated, []))
    trigger.assert_not_called()


def test_build_missing_circuit_assets_when_a_job_is_refused():
    circuits = [SimpleNamespace(id=uuid4(), scale=CircuitScale.small, assets=[]) for _ in range(3)]
    generated = [SimpleNamespace(id=circuit.id, type=EntityType.circuit) for circuit in circuits]

    with (
        patch.object(
            test_module, "trigger_asset_generation_task", side_effect=[uuid4(), None, uuid4()]
        ) as trigger,
        pytest.raises(ApiError) as e,
    ):
        test_module.build_missing_circuit_assets(after_success(generated, circuits))

    assert e.value.http_status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert str(circuits[1].id) in e.value.message
    assert trigger.call_count == len(circuits)
