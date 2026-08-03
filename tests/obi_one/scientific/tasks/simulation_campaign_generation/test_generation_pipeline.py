"""End-to-end behaviour of ``GenerateSimulationTask.execute``.

These tests pin the observable contract of a generation run: which files land in the coordinate
output directory, and what the top-level shape of ``simulation_config.json`` is for each family of
simulation config. They deliberately assert on whole dictionaries rather than individual keys, so
that a refactor which drops or renames a section fails loudly.
"""

import json

import pytest

import obi_one as obi
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    DEFAULT_BIOPHYSICAL_NODE_SET,
    DEFAULT_POINT_NODE_SET,
    build_config,
    generate,
)


class TestGeneratedFiles:
    def test_minimal_run_writes_config_and_node_sets_only(self, circuit_config, tmp_path):
        """With no morphology locations and no spike stimuli, only two files are written."""
        result = generate(circuit_config(), tmp_path)

        assert sorted(p.name for p in result.directory.iterdir()) == [
            "node_sets.json",
            "simulation_config.json",
        ]
        assert result.sonata_config["node_sets_file"] == "node_sets.json"
        assert "compartment_sets_file" not in result.sonata_config

    def test_file_names_are_declared_as_class_variables(self):
        """The task's file names are part of its public contract."""
        assert GenerateSimulationTask.CONFIG_FILE_NAME == "simulation_config.json"
        assert GenerateSimulationTask.NODE_SETS_FILE_NAME == "node_sets.json"
        assert GenerateSimulationTask.COMPARTMENT_SETS_FILE_NAME == "compartment_sets.json"

    def test_generated_config_is_valid_sonata(self, circuit_config, tmp_path):
        """``write_simulation_config`` validates through libsonata before writing."""
        result = generate(circuit_config(), tmp_path)

        # If libsonata had rejected the config, no file would exist to read back.
        assert result.sonata_config["version"] == pytest.approx(2.4)
        assert json.loads((result.directory / "simulation_config.json").read_text())

    def test_rerunning_into_the_same_directory_is_refused(self, circuit_config, tmp_path):
        """node_sets.json is written with ``overwrite_if_exists=False``, guarding stale output."""
        generate(circuit_config(), tmp_path)

        with pytest.raises(ValueError, match=r"node_sets.json' already exists!"):
            generate(circuit_config(), tmp_path)


class TestBaseSonataConfig:
    """The simulator-independent scaffolding every generated config starts from."""

    def test_circuit_simulation_sections(self, circuit_config, tmp_path):
        result = generate(
            circuit_config(
                initialize={"simulation_length": 250.0, "random_seed": 7, "v_init": -65.0}
            ),
            tmp_path,
        )

        assert result.sonata_config["version"] == pytest.approx(2.4)
        assert result.sonata_config["target_simulator"] == "NEURON"
        assert result.sonata_config["run"] == {"dt": 0.025, "random_seed": 7, "tstop": 250.0}
        assert result.sonata_config["output"] == {
            "output_dir": "output",
            "spikes_file": "spikes.h5",
        }

    def test_circuit_conditions(self, circuit_config, tmp_path):
        """A circuit simulation adds spike location, calcium and the synapse mechanisms."""
        result = generate(
            circuit_config(initialize={"extracellular_calcium_concentration": 1.3}), tmp_path
        )

        assert result.conditions == {
            "v_init": -80.0,
            "spike_location": "soma",
            "extracellular_calcium": 1.3,
            "mechanisms": {
                "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
                "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            },
        }

    def test_me_model_conditions_have_no_calcium_or_mechanisms(self, me_model_config, tmp_path):
        """An ME model is a single cell: there are no synapses to configure."""
        result = generate(me_model_config(), tmp_path)

        assert result.conditions == {"v_init": -80.0, "spike_location": "soma"}

    def test_brian2_conditions_have_no_spike_location(self, brian2_config, tmp_path):
        """``spike_location`` is added by the NEURON base class, not the Brian2 one."""
        result = generate(brian2_config(), tmp_path)

        assert result.conditions == {"v_init": -80.0}
        assert result.sonata_config["target_simulator"] == "Brian2"

    def test_learning_engine_uses_its_own_timestep(self, learning_engine_config, tmp_path):
        result = generate(learning_engine_config(), tmp_path)

        assert result.sonata_config["target_simulator"] == "LearningEngine"
        assert result.sonata_config["run"]["dt"] == pytest.approx(0.1)


class TestConfigFamilies:
    """Each simulation config family produces its own recognisable output."""

    def test_circuit_simulation_full_config(self, circuit_config, circuit, tmp_path):
        result = generate(circuit_config(), tmp_path)

        assert result.sonata_config == {
            "version": 2.4,
            "target_simulator": "NEURON",
            "run": {"dt": 0.025, "random_seed": 1, "tstop": 100.0},
            "conditions": {
                "v_init": -80.0,
                "spike_location": "soma",
                "extracellular_calcium": 1.1,
                "mechanisms": {
                    "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
                    "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
                },
            },
            "output": {"output_dir": "output", "spikes_file": "spikes.h5"},
            "network": str(circuit.path),
            "node_set": DEFAULT_BIOPHYSICAL_NODE_SET,
            "inputs": {},
            "reports": {},
            "node_sets_file": "node_sets.json",
        }

    def test_me_model_full_config(self, me_model_config, me_model_circuit, tmp_path):
        result = generate(me_model_config(), tmp_path)

        assert result.sonata_config == {
            "version": 2.4,
            "target_simulator": "NEURON",
            "run": {"dt": 0.025, "random_seed": 1, "tstop": 100.0},
            "conditions": {"v_init": -80.0, "spike_location": "soma"},
            "output": {"output_dir": "output", "spikes_file": "spikes.h5"},
            "network": str(me_model_circuit.path),
            "node_set": DEFAULT_BIOPHYSICAL_NODE_SET,
            "inputs": {},
            "reports": {},
            "node_sets_file": "node_sets.json",
        }

    def test_me_model_with_synapses_matches_circuit_shape(
        self, me_model_with_synapses_config, tmp_path
    ):
        """The with-synapses config derives from the circuit config, so it keeps the mechanisms."""
        result = generate(me_model_with_synapses_config(), tmp_path)

        assert result.conditions["extracellular_calcium"] == pytest.approx(1.1)
        assert set(result.conditions["mechanisms"]) == {"ProbAMPANMDA_EMS", "ProbGABAAB_EMS"}
        assert result.sonata_config["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_brian2_full_config(self, brian2_config, point_circuit, tmp_path):
        result = generate(brian2_config(), tmp_path)

        assert result.sonata_config == {
            "version": 2.4,
            "target_simulator": "Brian2",
            "run": {"dt": 0.025, "random_seed": 1, "tstop": 100.0},
            "conditions": {"v_init": -80.0},
            "output": {"output_dir": "output", "spikes_file": "spikes.h5"},
            "network": str(point_circuit.path),
            "node_set": DEFAULT_POINT_NODE_SET,
            "inputs": {},
            "reports": {},
            "node_sets_file": "node_sets.json",
        }

    def test_learning_engine_full_config(self, learning_engine_config, point_circuit, tmp_path):
        result = generate(learning_engine_config(), tmp_path)

        assert result.sonata_config == {
            "version": 2.4,
            "target_simulator": "LearningEngine",
            "run": {"dt": 0.1, "random_seed": 1, "tstop": 100.0},
            "conditions": {"v_init": -80.0},
            "output": {"output_dir": "output", "spikes_file": "spikes.h5"},
            "network": str(point_circuit.path),
            "node_set": DEFAULT_POINT_NODE_SET,
            "inputs": {},
            "reports": {},
            "node_sets_file": "node_sets.json",
        }


class TestStepOrdering:
    """``execute`` depends on its steps running in a particular order.

    These are the couplings a refactor is most likely to break, so they are asserted through
    observable output rather than by spying on the private methods.
    """

    def test_default_neuron_set_is_injected_before_node_sets_are_written(
        self, circuit_config, tmp_path
    ):
        """Resolving the simulation target adds a neuron set that must reach node_sets.json."""
        config = circuit_config()
        assert config.neuron_sets == {}

        result = generate(config, tmp_path)

        assert DEFAULT_BIOPHYSICAL_NODE_SET in config.neuron_sets
        assert DEFAULT_BIOPHYSICAL_NODE_SET in result.node_sets

    def test_locations_are_materialised_before_inputs_are_built(self, morphology_circuit, tmp_path):
        """The stimulus only knows its compartment set because materialisation ran first."""
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "ClampLocations": locations,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(neuron_set=locations.ref),
            },
        )

        result = generate(config, tmp_path)

        assert result.inputs["Clamp_0"]["compartment_set"] == "ClampLocations"
        assert result.sonata_config["compartment_sets_file"] == "compartment_sets.json"

    def test_the_simulation_target_is_resolved_before_the_blocks_that_default_to_it(
        self, circuit, tmp_path
    ):
        """``initialize.node_set`` is filled in first, so an untargeted recording inherits the
        same default rather than a second, differently-named one."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Voltage": obi.SomaVoltageRecording()},
        )

        result = generate(config, tmp_path)

        assert result.sonata_config["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert result.reports["Voltage"]["cells"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert len(config.neuron_sets) == 1
