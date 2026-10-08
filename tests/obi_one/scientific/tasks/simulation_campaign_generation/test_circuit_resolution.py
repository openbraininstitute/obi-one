"""How the task turns the config's circuit field into a staged circuit and a ``network`` path.

A locally-pathed circuit is referenced in place; a database-backed one is staged to disk first,
and the ``network`` entry then becomes a path relative to the coordinate output directory so the
generated config stays relocatable.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import obi_one as obi
from obi_one.core.exception import ConfigValidationError, OBIONEError
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    MORPHOLOGY_CIRCUIT_PATH,
    MULTI_POPULATION_CIRCUIT_PATH,
    FakeDBClient,
    RecordedCall,
    build_config,
    generate,
)

CIRCUIT_ID = "11111111-2222-3333-4444-555555555555"
OTHER_CIRCUIT_ID = "66666666-7777-8888-9999-000000000000"
ARRAY_ID = "9f8ac5a5-4b6c-4e57-9a2f-2e3f7d0b1c44"


@pytest.fixture
def staging_recorder(monkeypatch):
    """Replace ``CircuitFromID.stage_circuit`` with a recorder returning the local test circuit.

    Real staging downloads assets from entitycore. Everything the task depends on is the returned
    ``Circuit`` and the directory it was asked to stage into, so both are captured here.
    """
    calls: list[dict] = []

    def _stage_circuit(self, *, dest_dir=Path(), db_client=None, entity_cache=False, **kwargs):
        calls.append(
            {
                "dest_dir": Path(dest_dir),
                "entity_cache": entity_cache,
                "db_client": db_client,
                **kwargs,
            }
        )
        return Circuit(name=str(self), path=str(MULTI_POPULATION_CIRCUIT_PATH))

    monkeypatch.setattr(CircuitFromID, "stage_circuit", _stage_circuit)
    return calls


class TestLocalCircuit:
    def test_network_is_the_absolute_circuit_config_path(self, circuit_config, circuit, tmp_path):
        result = generate(circuit_config(), tmp_path)

        assert result.sonata_config["network"] == str(Path(circuit.path).resolve())

    def test_a_relative_circuit_path_is_resolved(self, tmp_path):
        relative_path = os.path.relpath(MULTI_POPULATION_CIRCUIT_PATH, Path.cwd())
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=obi.Circuit(name="relative", path=relative_path),
        )

        result = generate(config, tmp_path)

        assert Path(result.sonata_config["network"]).is_absolute()
        assert Path(result.sonata_config["network"]).exists()

    def test_the_resolved_circuit_is_kept_on_the_task(self, circuit_config, tmp_path):
        config = circuit_config()
        coordinate_root = tmp_path / "0"
        coordinate_root.mkdir(parents=True)
        config.scan_output_root = tmp_path
        config.coordinate_output_root = coordinate_root

        task = GenerateSimulationTask(config=config)
        task.execute()

        assert isinstance(task._circuit, Circuit)


class TestCircuitFromID:
    def _config(self):
        return build_config(CircuitSimulationSingleConfig, circuit=CircuitFromID(id_str=CIRCUIT_ID))

    def test_circuit_is_staged_into_the_coordinate_directory(
        self, staging_recorder, tmp_path, db_client
    ):
        generate(self._config(), tmp_path, db_client=db_client)

        assert staging_recorder[0]["dest_dir"] == tmp_path / "0" / "sonata_circuit"
        assert staging_recorder[0]["entity_cache"] is False

    def test_only_the_nodes_are_staged(self, staging_recorder, tmp_path, db_client):
        """Generation reads node properties and node sets, never the edges.

        Edge files dominate a large circuit, and a private-project circuit has to be downloaded
        rather than symlinked, so staging them would be a wasted download.
        """
        generate(self._config(), tmp_path, db_client=db_client)

        assert staging_recorder[0]["nodes_only"] is True

    def test_a_morphology_location_target_needs_the_whole_circuit(
        self, monkeypatch, tmp_path, db_client
    ):
        """Morphology locations become compartment sets, which walk each neuron's morphology."""
        calls: list[dict] = []

        def _stage_circuit(self, **kwargs):
            calls.append(kwargs)
            return Circuit(name=str(self), path=str(MORPHOLOGY_CIRCUIT_PATH))

        monkeypatch.setattr(CircuitFromID, "stage_circuit", _stage_circuit)

        locations = obi.RandomMorphologyLocations(
            random_seed=0, number_of_locations=2, section_types=(3, 4)
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=CircuitFromID(id_str=CIRCUIT_ID),
            blocks={
                "Locations": locations,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    neuron_set=locations.ref, amplitude=0.2, duration=50.0
                ),
            },
        )

        result = generate(config, tmp_path, db_client=db_client)

        assert set(result.compartment_sets) == {"Locations"}
        assert calls[0].get("nodes_only") is not True

    def test_entity_cache_stages_into_a_shared_scan_level_directory(
        self, staging_recorder, tmp_path, db_client
    ):
        """With the cache on, the circuit is staged once per entity for the whole scan."""
        generate(self._config(), tmp_path, db_client=db_client, entity_cache=True)

        assert staging_recorder[0]["dest_dir"] == (
            tmp_path / "entity_cache" / "sonata_circuit" / CIRCUIT_ID
        )
        assert staging_recorder[0]["entity_cache"] is True

    @pytest.mark.usefixtures("staging_recorder")
    def test_network_becomes_a_relative_path(self, tmp_path, db_client):
        """A staged circuit is referenced relatively so the output directory can be moved."""
        result = generate(self._config(), tmp_path, db_client=db_client)

        network = result.sonata_config["network"]
        assert not Path(network).is_absolute()
        assert (result.directory / network).resolve() == MULTI_POPULATION_CIRCUIT_PATH.resolve()

    def test_the_db_client_is_passed_through_to_staging(
        self, staging_recorder, tmp_path, db_client
    ):
        generate(self._config(), tmp_path, db_client=db_client)

        assert staging_recorder[0]["db_client"] is db_client


@dataclass
class _ArrayDBClient(FakeDBClient):
    """A recorder that also serves the recording array, as built for ``array_circuit_id``."""

    array_circuit_id: str = CIRCUIT_ID

    def get_entity(self, *, entity_id, entity_type):
        self.calls.append(
            RecordedCall(
                method="get_entity", kwargs={"entity_id": entity_id, "entity_type": entity_type}
            )
        )
        return SimpleNamespace(id=UUID(entity_id), circuit_id=UUID(self.array_circuit_id))


@pytest.mark.usefixtures("staging_recorder")
class TestRecordingArrayCircuit:
    """An LFP recording's array must have been built for the circuit being simulated."""

    def _config(self):
        return build_config(
            CircuitSimulationSingleConfig,
            circuit=CircuitFromID(id_str=CIRCUIT_ID),
            blocks={
                "LFP": obi.ExtracellularElectrodeArrayRecordingBlock(
                    electrode_array=obi.SimulatableExtracellularRecordingArrayFromID(
                        id_str=ARRAY_ID
                    )
                )
            },
        )

    def test_an_array_built_for_the_simulated_circuit_is_accepted(self, tmp_path):
        result = generate(self._config(), tmp_path, db_client=_ArrayDBClient())

        assert result.reports["LFP"]["electrodes_file"] == f"{ARRAY_ID}.h5"

    def test_an_array_built_for_another_circuit_is_refused(self, tmp_path):
        """The UI only offers the circuit's own arrays, but a config can come from elsewhere."""
        db_client = _ArrayDBClient(array_circuit_id=OTHER_CIRCUIT_ID)

        with pytest.raises(ConfigValidationError, match=f"built for circuit '{OTHER_CIRCUIT_ID}'"):
            generate(self._config(), tmp_path, db_client=db_client)

    def test_the_refusal_comes_before_anything_is_written(self, tmp_path):
        db_client = _ArrayDBClient(array_circuit_id=OTHER_CIRCUIT_ID)

        with pytest.raises(ConfigValidationError):
            generate(self._config(), tmp_path, db_client=db_client)

        assert db_client.calls_to("update_entity") == []
        assert db_client.calls_to("upload_file") == []


class TestCircuitResolutionErrors:
    def test_a_config_without_a_circuit_is_refused(self, circuit_config, tmp_path):
        config = circuit_config()
        del config.initialize.__dict__["circuit"]

        with pytest.raises(OBIONEError, match="No circuit specified in config!"):
            generate(config, tmp_path)

    def test_an_unrecognised_circuit_type_is_refused(self, circuit_config, tmp_path):
        """Only ``Circuit`` and the known ``*FromID`` wrappers can be resolved."""
        config = circuit_config()
        config.initialize.__dict__["circuit"] = object()

        with pytest.raises(OBIONEError, match="Failed to resolve circuit!"):
            generate(config, tmp_path)
