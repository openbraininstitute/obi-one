"""How the task turns the config's circuit field into a staged circuit and a ``network`` path.

A locally-pathed circuit is referenced in place; a database-backed one is staged to disk first,
and the ``network`` entry then becomes a path relative to the coordinate output directory so the
generated config stays relocatable.
"""

import os
from pathlib import Path

import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    MULTI_POPULATION_CIRCUIT_PATH,
    build_config,
    generate,
)

CIRCUIT_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def staging_recorder(monkeypatch):
    """Replace ``CircuitFromID.stage_circuit`` with a recorder returning the local test circuit.

    Real staging downloads assets from entitycore. Everything the task depends on is the returned
    ``Circuit`` and the directory it was asked to stage into, so both are captured here.
    """
    calls: list[dict] = []

    def _stage_circuit(self, *, dest_dir=Path(), db_client=None, entity_cache=False):
        calls.append(
            {"dest_dir": Path(dest_dir), "entity_cache": entity_cache, "db_client": db_client}
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
