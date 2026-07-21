from unittest.mock import MagicMock
from uuid import UUID

import pytest

from obi_one.core.info import Info
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.library.simulation.schemas import (
    NeurodamusMechanismBuild,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # noqa: E501
    MEModelWithSynapsesCircuitSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.single_neuron_synaptome_simulation_execution import (  # noqa: E501
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
)

_BASE = "obi_one.scientific.tasks.simulation_execution.base"
_SYNAPTOME = (
    "obi_one.scientific.tasks.simulation_execution.single_neuron_synaptome_simulation_execution"
)


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = UUID("12345678-1234-5678-1234-567812345678")
    return entity


@pytest.fixture
def generation_config(tmp_path, simulation_entity):
    config = MEModelWithSynapsesCircuitSimulationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=MEModelWithSynapsesCircuitSimulationScanConfig.Initialize(
            circuit=MEModelWithSynapsesCircuitFromID(id_str="circuit-id"),
        ),
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    config.set_single_entity(simulation_entity)
    return config


@pytest.fixture
def config(tmp_path, simulation_entity):
    task_config = SingleNeuronSynaptomeSimulationExecutionSingleConfig(
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    task_config.set_single_entity(simulation_entity)
    return task_config


@pytest.fixture
def db_client():
    return MagicMock()


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy")
    return path


def _neurodamus_mechanism_build(tmp_path):
    return NeurodamusMechanismBuild(
        libnrnmech_path=_touch(tmp_path / "libnrnmech.so"),
        libcorenrnmech_path=_touch(tmp_path / "libcorenrnmech.so"),
        special_binary_path=_touch(tmp_path / "special"),
    )
