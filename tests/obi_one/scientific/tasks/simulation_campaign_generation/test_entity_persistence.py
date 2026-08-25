"""What the task sends to entitycore when a database client is supplied.

Generation is usable offline: with no client it only writes files. With one, it additionally
records the neuron count on the Simulation entity and uploads the generated artefacts as labelled
assets. Both the set of labels and the neuron count are part of the contract.
"""

import entitysdk
import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BIOPHYSICAL_POPULATION,
    VIRTUAL_POPULATION,
    FakeDBClient,
    build_config,
    generate,
)


class TestWithoutADatabaseClient:
    def test_generation_works_offline(self, circuit_config, tmp_path):
        result = generate(circuit_config(), tmp_path)

        assert (result.directory / "simulation_config.json").exists()

    def test_nothing_is_uploaded(self, circuit_config, tmp_path, db_client):
        generate(circuit_config(), tmp_path, db_client=None)

        assert db_client.calls == []


class TestAssetUploads:
    def test_node_sets_and_config_are_uploaded(self, circuit_config, tmp_path, db_client):
        generate(circuit_config(), tmp_path, db_client=db_client)

        assert db_client.uploaded_labels() == ["custom_node_sets", "sonata_simulation_config"]

    def test_uploads_point_at_the_generated_files(self, circuit_config, tmp_path, db_client):
        result = generate(circuit_config(), tmp_path, db_client=db_client)

        paths = {
            call.kwargs["asset_label"]: call.kwargs["file_path"]
            for call in db_client.calls_to("upload_file")
        }
        assert paths["custom_node_sets"] == result.directory / "node_sets.json"
        assert paths["sonata_simulation_config"] == result.directory / "simulation_config.json"

    def test_uploads_target_the_simulation_entity(self, circuit_config, tmp_path, db_client):
        config = circuit_config()

        generate(config, tmp_path, db_client=db_client)

        for call in db_client.calls_to("upload_file"):
            assert call.kwargs["entity_id"] == config.single_entity.id
            assert call.kwargs["entity_type"] is entitysdk.models.Simulation

    def test_json_assets_declare_a_json_content_type(self, circuit_config, tmp_path, db_client):
        generate(circuit_config(), tmp_path, db_client=db_client)

        for call in db_client.calls_to("upload_file"):
            assert call.kwargs["file_content_type"] == "application/json"

    def test_compartment_sets_are_uploaded_when_present(
        self, morphology_circuit, tmp_path, db_client
    ):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(neuron_set=locations.ref),
            },
        )

        generate(config, tmp_path, db_client=db_client)

        assert "compartment_sets" in db_client.uploaded_labels()

    def test_spike_replay_files_are_uploaded(self, circuit, tmp_path, db_client):
        source = VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="source", elements=[0, 1, 2]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Source": source,
                "Spikes": lambda: obi.PoissonSpikeStimulus(source_neuron_set=source.ref),
            },
        )

        result = generate(config, tmp_path, db_client=db_client)

        replay_calls = [
            call
            for call in db_client.calls_to("upload_file")
            if call.kwargs["asset_label"] == "replay_spikes"
        ]
        assert len(replay_calls) == 1
        assert replay_calls[0].kwargs["file_path"] == result.directory / "Spikes_spikes.h5"
        assert replay_calls[0].kwargs["file_content_type"] == "application/x-hdf5"

    def test_one_replay_upload_per_spike_stimulus(self, circuit, tmp_path, db_client):
        source = VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="source", elements=[0, 1, 2]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Source": source,
                "Poisson": lambda: obi.PoissonSpikeStimulus(source_neuron_set=source.ref),
                "Synchronous": lambda: obi.FullySynchronousSpikeStimulus(
                    source_neuron_set=source.ref
                ),
            },
        )

        generate(config, tmp_path, db_client=db_client)

        assert db_client.uploaded_labels().count("replay_spikes") == 2

    def test_a_config_without_spikes_uploads_no_replay_assets(
        self, circuit_config, tmp_path, db_client
    ):
        generate(circuit_config(), tmp_path, db_client=db_client)

        assert "replay_spikes" not in db_client.uploaded_labels()


class TestNeuronCount:
    def test_the_simulation_target_size_is_recorded(self, circuit, tmp_path, db_client):
        target = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="target", elements=[0, 1, 2, 3]),
        )
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Target": target}
        )
        config.initialize.node_set = config.neuron_sets["Target"].ref

        generate(config, tmp_path, db_client=db_client)

        updates = db_client.calls_to("update_entity")
        assert len(updates) == 1
        assert updates[0].kwargs["attrs_or_entity"] == {"number_neurons": 4}

    def test_the_default_target_counts_the_whole_population(
        self, circuit_config, tmp_path, db_client
    ):
        generate(circuit_config(), tmp_path, db_client=db_client)

        updates = db_client.calls_to("update_entity")
        assert updates[0].kwargs["attrs_or_entity"] == {"number_neurons": 10}

    def test_an_me_model_always_counts_one_neuron(self, me_model_config, tmp_path, db_client):
        """An ME model config has no neuron_sets dictionary, so the count is fixed at one."""
        generate(me_model_config(), tmp_path, db_client=db_client)

        updates = db_client.calls_to("update_entity")
        assert updates[0].kwargs["attrs_or_entity"] == {"number_neurons": 1}

    def test_the_update_targets_the_simulation_entity(self, circuit_config, tmp_path, db_client):
        config = circuit_config()

        generate(config, tmp_path, db_client=db_client)

        update = db_client.calls_to("update_entity")[0]
        assert update.kwargs["entity_id"] == config.single_entity.id
        assert update.kwargs["entity_type"] is entitysdk.models.Simulation


class TestPersistenceOrdering:
    def test_the_neuron_count_is_recorded_before_the_assets_are_uploaded(
        self, circuit_config, tmp_path, db_client
    ):
        generate(circuit_config(), tmp_path, db_client=db_client)

        methods = [call.method for call in db_client.calls]
        assert methods[0] == "update_entity"
        assert set(methods[1:]) == {"upload_file"}

    def test_the_config_is_uploaded_last(self, circuit_config, tmp_path, db_client):
        """The SONATA config is the completion marker, so it is uploaded after its inputs."""
        generate(circuit_config(), tmp_path, db_client=db_client)

        assert db_client.uploaded_labels()[-1] == "sonata_simulation_config"


class TestSingleEntityRequirement:
    def test_persisting_without_a_registered_entity_fails(self, circuit_config, tmp_path):
        """``single_entity`` is populated by the scan before the task runs."""
        config = circuit_config()
        coordinate_root = tmp_path / "0"
        coordinate_root.mkdir(parents=True)
        config.scan_output_root = tmp_path
        config.coordinate_output_root = coordinate_root

        with pytest.raises(AttributeError):
            GenerateSimulationTask(config=config).execute(db_client=FakeDBClient())
