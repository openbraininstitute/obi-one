from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.scan import Scan

from obi.modeling.circuit.circuit import Circuit
from obi.modeling.circuit.neuron_sets import NeuronSet
from obi.modeling.circuit.synapse_sets import SynapseSet
from obi.modeling.circuit.intracellular_location_sets import IntracellularLocationSet
from obi.modeling.circuit.extracellular_location_sets import ExtracellularLocationSet

from obi.modeling.simulation.stimulus import Stimulus
from obi.modeling.simulation.timestamps import Timestamps
from obi.modeling.simulation.recording import Recording

from pydantic import PrivateAttr
import os, json

class SimulationsForm(Form):
    """
    """

    single_coord_class_name: str = "Simulation"

    timestamps: dict[str, Timestamps]
    stimuli: dict[str, Stimulus]
    recordings: dict[str, Recording]
    neuron_sets: dict[str, NeuronSet]
    synapse_sets: dict[str, SynapseSet]
    # intracellular_location_sets: dict[str, IntracellularLocationSet]
    # extracellular_location_sets: dict[str, ExtracellularLocationSet]

    class Initialize(Block):
        circuit: Circuit
        simulation_length: list[float] | float = 100.0
        random_seed: list[int] | int = 1
        extracellular_calcium_concentration: list[float] | float = 1.1
        v_init: list[float] | float = -80.0

        sonata_version: list[int] | int = 1
        target_simulator: list[str] | str = 'CORENEURON'
        timestep: list[float] | float = 0.025

    initialize: Initialize


class Simulation(SimulationsForm, SingleCoordinateMixin):
    """Only allows single float values and ensures nested attributes follow the same rule."""
    pass

    def generate(self):

        self._sonata_config = {}
        self._sonata_config['version'] = self.initialize.sonata_version
        self._sonata_config['target_simulator'] = self.initialize.target_simulator

        self._sonata_config['network'] = self.initialize.circuit.circuit_path
        self._sonata_config["node_set"] = self.initialize.circuit.node_set

        self._sonata_config['run'] = {}
        self._sonata_config['run']['dt'] = self.initialize.timestep
        self._sonata_config['run']['random_seed'] = self.initialize.random_seed
        self._sonata_config['run']['tstop'] = self.initialize.simulation_length

        self._sonata_config['conditions'] = {}
        self._sonata_config['conditions']['extracellular_calcium'] = self.initialize.extracellular_calcium_concentration
        self._sonata_config['conditions']['v_init'] = self.initialize.v_init

        self._sonata_config['conditions']['mechanisms'] = {
            "ProbAMPANMDA_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            },
            "ProbGABAAB_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            }
        }

        self._sonata_config['reports'] = {}
        for recording_key, recording in self.recordings.items():
            self._sonata_config['reports'][recording_key] = recording.generate_config()

        os.makedirs(self.coordinate_output_root, exist_ok=True)
        simulation_config_path = os.path.join(self.coordinate_output_root, f"simulation_config.json")
        with open(simulation_config_path, 'w') as f:
            json.dump(self._sonata_config, f, indent=2)
