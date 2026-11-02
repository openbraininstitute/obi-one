from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import entitysdk
import pytest

from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import circuit_simplification as test_module
from obi_one.scientific.library.circuit_constants import NodePopulationType
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsNodePopulation,
    CircuitMetricsOutput,
)

MODULE = "app.services.resource_estimation.circuit_simplification"


@pytest.fixture
def db_client():
    """Database client."""
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # ruff: ignore[hardcoded-password-func-arg]


def _metrics(nbio: int) -> CircuitMetricsOutput:
    """Minimal metrics output: one biophysical population of ``nbio`` nodes."""
    pop = CircuitMetricsNodePopulation(
        number_of_nodes=nbio,
        name="bio_pop",
        population_type=NodePopulationType.biophysical,
        property_names=[],
        property_unique_values={},
        property_value_counts={},
        node_location_info=None,
    )
    return CircuitMetricsOutput(
        number_of_biophys_node_populations=1,
        number_of_virtual_node_populations=0,
        number_of_point_node_populations=0,
        names_of_biophys_node_populations=["bio_pop"],
        names_of_virtual_node_populations=[],
        names_of_point_node_populations=[],
        names_of_nodesets=[],
        biophysical_node_populations=[pop],
        virtual_node_populations=[],
        point_node_populations=[],
        number_of_chemical_edge_populations=0,
        number_of_electrical_edge_populations=0,
        names_of_chemical_edge_populations=[],
        names_of_electrical_edge_populations=[],
        chemical_edge_populations=[],
        electrical_edge_populations=[],
    )


_UNSET = object()


def _run_estimate(db_client, metrics, algorithm_names, asset_id=_UNSET):
    """Run estimate_task_resources with mocked DB/metrics dependencies."""
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simplification]
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simplification, config_id=uuid4())
    fake_entity = SimpleNamespace(inputs=[SimpleNamespace(id=uuid4())])
    fake_single_config = SimpleNamespace(
        algorithms={n: SimpleNamespace(algorithm_name=n) for n in algorithm_names}
    )
    with (
        patch.object(db_client, "get_entity", return_value=fake_entity),
        patch.object(db_client, "download_content", return_value=b'{"type": "Fake"}'),
        patch(f"{MODULE}.get_circuit_metrics", return_value=metrics),
        patch(
            f"{MODULE}.get_task_spec_for_task_type",
            return_value=SimpleNamespace(asset_label="circuit_simplification_config"),
        ),
        patch(
            f"{MODULE}.deserialize_obi_object_from_json_data",
            return_value=SimpleNamespace(model_dump=dict),
        ),
        patch(f"{MODULE}.CircuitSimplificationSingleConfig") as single_config_cls,
        patch(f"{MODULE}.db_sdk.get_entity_asset_by_label") as get_asset,
    ):
        get_asset.return_value = SimpleNamespace(id=uuid4() if asset_id is _UNSET else asset_id)
        single_config_cls.model_validate.return_value = fake_single_config
        return test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )


def test_estimate_task_resources_point_neuron(db_client):
    resources = _run_estimate(db_client, _metrics(nbio=10_000), ["lif_nest"])

    # nbio=10_000: 10_000/500_000 -> 1 core; memory = 2 + 1*2 = 4 GB
    assert resources.cores == 1
    assert resources.memory == 4
    assert resources.timelimit == "01:00"
    assert resources.compute_cell == "cell_b"


def test_estimate_task_resources_single_compartment_scales(db_client):
    resources = _run_estimate(db_client, _metrics(nbio=200_000), ["single_compartment"])

    # 200k cells x 100 locations = 20M units -> capped at 16 cores;
    # memory = 2 + 16*2 = 34 GB -> 16-core preset gives 64 GB;
    # time = 20M / (16 x 100k) = 12.5 h -> 13
    assert resources.cores == 16
    assert resources.memory == 64
    assert resources.timelimit == "13:00"


def test_estimate_task_resources_sums_algorithm_times(db_client):
    resources = _run_estimate(
        db_client, _metrics(nbio=200_000), ["single_compartment", "neuron_reduce"]
    )

    # timelimit is the sum over sequentially-run algorithms:
    # single_compartment 12.5 h + neuron_reduce 200k/(16 x 1000) = 12.5 h -> 25
    assert resources.cores == 16
    assert resources.timelimit == "25:00"


def test_estimate_task_resources_missing_asset_id(db_client):
    with pytest.raises(ValueError, match="Config asset must have an id"):
        _run_estimate(db_client, _metrics(nbio=10), ["lif_nest"], asset_id=None)
