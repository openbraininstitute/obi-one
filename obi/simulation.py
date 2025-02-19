from .multi_template import MultiTemplate
from .circuit import Circuit
from .circuit_grouping import CircuitGrouping
from .timestamps import Timestamps
from .stimulus import Stimulus
from .recording import Recording

from pydantic import BaseModel

class Simulation(MultiTemplate):

    circuit_groupings: dict[str, CircuitGrouping]
    timestamps: dict[str, Timestamps]
    stimuli: dict[str, Stimulus]
    recordings: dict[str, Recording]

    class Initialization(BaseModel):
        circuit: Circuit
        simulation_length: float = 100.0
        random_seed: int = 1
        extracellular_calcium_concentration: float = 1.1
        v_init: float = -80.0


        sonata_version: int = 1
        target_simulator: str = 'CORENEURON'
        timestep: float = 0.025

    initialize: Initialization

        

    



    def sonata_config(self):

        self._sonata_config = {}
        self._sonata_config['version'] = self.sonata_version
        self._sonata_config['target_simulator'] = self.target_simulator

        self._sonata_config['network'] = self.circuit.circuit_path
        self._sonata_config["node_set"] = self.circuit.node_set

        self._sonata_config['run'] = {}
        self._sonata_config['run']['dt'] = self.timestep
        self._sonata_config['run']['random_seed'] = self.random_seed
        self._sonata_config['run']['tstop'] = self.simulation_length

        self._sonata_config['conditions'] = {}
        self._sonata_config['conditions']['extracellular_calcium'] = self.extracellular_calcium_concentration
        self._sonata_config['conditions']['v_init'] = self.v_init
        self._sonata_config['conditions']['extracellular_calcium']

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
            self._sonata_config['reports'][recording_key] = recording.sonata_config()

        return self._sonata_config