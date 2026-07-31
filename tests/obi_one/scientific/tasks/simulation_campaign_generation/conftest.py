"""Shared fixtures for the simulation generation tests.

The tests in this package drive ``GenerateSimulationTask`` directly rather than through a scan.
A ``SingleConfig`` is assembled by hand (``empty_config`` -> ``set``/``add`` ->
``fill_block_references_and_names``), pointed at a temporary output directory, and executed. That
keeps every test a black-box check of "config in, SONATA artefacts out", so the suite survives a
refactor of the task's internals.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import obi_one as obi
from obi_one.scientific.library.memodel_circuit import (
    MEModelCircuit,
    MEModelWithSynapsesCircuit,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (
    LearningEngineCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # ruff: ignore[line-too-long]
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask

from tests.utils import CIRCUIT_DIR, SINGLE_NEURON_CIRCUIT_DIR

# A biophysical circuit with 10 neurons in `S1nonbarrel_neurons` plus the `VPM` and `POm` virtual
# populations -- enough to exercise biophysical, virtual and multi-population neuron sets.
MULTI_POPULATION_CIRCUIT_PATH = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"

# A circuit with detailed morphologies, needed by the morphology-location blocks.
MORPHOLOGY_CIRCUIT_PATH = CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5" / "circuit_config.json"

# A single-neuron circuit, used for the ME-model configs.
SINGLE_NEURON_CIRCUIT_PATH = (
    SINGLE_NEURON_CIRCUIT_DIR / "SingleNeuronCircuit__top_nodes_dim6__IDX0" / "circuit_config.json"
)

# The synthetic FlyWire-style point circuit: one `brian2_point` population `drosophila` with 3
# neurons and a `sugar` node set covering neurons 0 and 1.
POINT_CIRCUIT_PATH = (
    Path(__file__).parents[2] / "library" / "simulation" / "data" / "circuit_config.json"
)

BIOPHYSICAL_POPULATION = "S1nonbarrel_neurons"
VIRTUAL_POPULATION = "VPM"
POINT_POPULATION = "drosophila"

DEFAULT_BIOPHYSICAL_NODE_SET = "Default: All Biophysical Neurons"
DEFAULT_VIRTUAL_NODE_SET = "Default: All Virtual Neurons"
DEFAULT_POINT_NODE_SET = "Default: All Point Neurons"
DEFAULT_BRIAN2_STIMULUS_NODE_SET = "Default: Sugar gustatory receptor neurons"


@dataclass
class GeneratedSimulation:
    """Everything a generation run wrote to disk, already parsed."""

    directory: Path
    sonata_config: dict
    node_sets: dict
    compartment_sets: dict | None

    @property
    def inputs(self) -> dict:
        return self.sonata_config["inputs"]

    @property
    def reports(self) -> dict:
        return self.sonata_config["reports"]

    @property
    def conditions(self) -> dict:
        return self.sonata_config["conditions"]


@dataclass
class RecordedCall:
    """A single method call captured by :class:`FakeDBClient`."""

    method: str
    kwargs: dict


@dataclass
class FakeDBClient:
    """Records the entitysdk calls the task makes, without touching a database.

    ``GenerateSimulationTask`` only ever calls ``update_entity`` and ``upload_file`` on the
    client, and only when one is supplied, so a recorder is enough to pin the persistence
    behaviour.
    """

    calls: list[RecordedCall] = field(default_factory=list)

    def update_entity(self, **kwargs: Any) -> None:
        self.calls.append(RecordedCall(method="update_entity", kwargs=kwargs))

    def upload_file(self, **kwargs: Any) -> None:
        self.calls.append(RecordedCall(method="upload_file", kwargs=kwargs))

    def calls_to(self, method: str) -> list[RecordedCall]:
        return [call for call in self.calls if call.method == method]

    def uploaded_labels(self) -> list[str]:
        return [call.kwargs["asset_label"] for call in self.calls_to("upload_file")]


@dataclass
class _StubEntity:
    """Stands in for the registered ``entitysdk`` Simulation entity."""

    id: str = "00000000-0000-0000-0000-000000000000"


def build_config(
    config_class: type,
    *,
    circuit: Any,
    blocks: dict[str, Any] | None = None,
    initialize: dict[str, Any] | None = None,
    root_blocks: dict[str, Any] | None = None,
) -> Any:
    """Assemble a SingleConfig without going through a scan.

    ``blocks`` maps the name a block is registered under to the block itself, applied in insertion
    order. A value may also be a callable taking no arguments and returning the block; it is
    invoked at add time, which is how a block gets to reference the ``.ref`` of one added before
    it (``.ref`` only exists once ``add`` has run). ``initialize`` supplies extra keyword arguments
    for the config's ``Initialize`` block.
    """
    config = config_class.empty_config()
    config.set(
        obi.Info(campaign_name="Test campaign", campaign_description="Test description"),
        name="info",
    )

    for name, block_or_factory in (blocks or {}).items():
        block = block_or_factory() if callable(block_or_factory) else block_or_factory
        config.add(block, name=name)

    for name, block in (root_blocks or {}).items():
        config.set(block, name=name)

    config.set(
        config_class.Initialize(
            circuit=circuit,
            **{"simulation_length": 100.0, **(initialize or {})},
        ),
        name="initialize",
    )

    config.fill_block_references_and_names()
    return config


def generate(
    config: Any,
    tmp_path: Path,
    *,
    db_client: Any = None,
    entity_cache: bool = False,
    subdirectory: str = "0",
) -> GeneratedSimulation:
    """Run ``GenerateSimulationTask`` on ``config`` and parse everything it wrote."""
    coordinate_root = tmp_path / subdirectory
    coordinate_root.mkdir(parents=True, exist_ok=True)

    config.idx = 0
    config.scan_output_root = tmp_path
    config.coordinate_output_root = coordinate_root
    if db_client is not None:
        config.set_single_entity(_StubEntity())

    GenerateSimulationTask(config=config).execute(db_client=db_client, entity_cache=entity_cache)

    return read_generated(coordinate_root)


def read_generated(coordinate_root: Path) -> GeneratedSimulation:
    """Parse the artefacts a generation run left in ``coordinate_root``."""
    compartment_sets_path = coordinate_root / "compartment_sets.json"

    return GeneratedSimulation(
        directory=coordinate_root,
        sonata_config=json.loads((coordinate_root / "simulation_config.json").read_text()),
        node_sets=json.loads((coordinate_root / "node_sets.json").read_text()),
        compartment_sets=(
            json.loads(compartment_sets_path.read_text())
            if compartment_sets_path.exists()
            else None
        ),
    )


@pytest.fixture
def circuit():
    """A 10-neuron biophysical circuit with virtual VPM/POm populations."""
    return obi.Circuit(name="N_10__top_nodes_dim6", path=str(MULTI_POPULATION_CIRCUIT_PATH))


@pytest.fixture
def morphology_circuit():
    """A circuit with detailed morphologies, for morphology-location targeting."""
    return obi.Circuit(name="nbS1-O1-E2Sst-maxNsyn-HEX0-L5", path=str(MORPHOLOGY_CIRCUIT_PATH))


@pytest.fixture
def me_model_circuit():
    """A single-neuron circuit for the ME-model config."""
    return MEModelCircuit(name="me_model", path=str(SINGLE_NEURON_CIRCUIT_PATH))


@pytest.fixture
def me_model_with_synapses_circuit():
    """A single-neuron circuit with synapses for the ME-model-with-synapses config."""
    return MEModelWithSynapsesCircuit(
        name="me_model_with_synapses", path=str(SINGLE_NEURON_CIRCUIT_PATH)
    )


@pytest.fixture
def point_circuit():
    """The synthetic drosophila point-neuron circuit used by Brian2 and LearningEngine."""
    return obi.Circuit(name="drosophila", path=str(POINT_CIRCUIT_PATH))


@pytest.fixture
def db_client():
    """A recording stand-in for an entitysdk client."""
    return FakeDBClient()


@pytest.fixture
def circuit_config(circuit):
    """Factory building a ``CircuitSimulationSingleConfig`` on the biophysical circuit."""

    def _build(**kwargs):
        return build_config(CircuitSimulationSingleConfig, circuit=circuit, **kwargs)

    return _build


@pytest.fixture
def me_model_config(me_model_circuit):
    """Factory building an ``MEModelSimulationSingleConfig``."""

    def _build(**kwargs):
        return build_config(MEModelSimulationSingleConfig, circuit=me_model_circuit, **kwargs)

    return _build


@pytest.fixture
def me_model_with_synapses_config(me_model_with_synapses_circuit):
    """Factory building an ``MEModelWithSynapsesCircuitSimulationSingleConfig``."""

    def _build(**kwargs):
        return build_config(
            MEModelWithSynapsesCircuitSimulationSingleConfig,
            circuit=me_model_with_synapses_circuit,
            **kwargs,
        )

    return _build


@pytest.fixture
def brian2_config(point_circuit):
    """Factory building a ``Brian2CircuitSimulationSingleConfig``."""

    def _build(**kwargs):
        return build_config(Brian2CircuitSimulationSingleConfig, circuit=point_circuit, **kwargs)

    return _build


@pytest.fixture
def learning_engine_config(point_circuit):
    """Factory building a ``LearningEngineCircuitSimulationSingleConfig``."""

    def _build(**kwargs):
        return build_config(
            LearningEngineCircuitSimulationSingleConfig, circuit=point_circuit, **kwargs
        )

    return _build
