from ..core.template import Template, SubTemplate, SingleTypeMixin
from ..core.parameter_scan import ParameterScan

from ..circuit.circuit import Circuit
from ..circuit.neuron_sets import NeuronSet
from ..circuit.synapse_sets import SynapseSet
from ..circuit.intracellular_location_sets import IntracellularLocationSet
from ..circuit.extracellular_location_sets import ExtracellularLocationSet

from .stimulus import Stimulus
from .timestamps import Timestamps
from .recording import Recording

class SimulationParameterScanTemplate(Template):
    """Base simulation model that contains a generic nested object."""

    timestamps: dict[str, Timestamps]
    stimuli: dict[str, Stimulus]
    recordings: dict[str, Recording]
    neuron_sets: dict[str, NeuronSet]
    synapse_sets: dict[str, SynapseSet]
    intracellular_location_sets: dict[str, IntracellularLocationSet]
    extracellular_location_sets: dict[str, ExtracellularLocationSet]

    class Initialization(SubTemplate):
        circuit: Circuit
        simulation_length: list[float] | float = 100.0
        random_seed: int = 1
        extracellular_calcium_concentration: float = 1.1
        v_init: float = -80.0

        sonata_version: int = 1
        target_simulator: str = 'CORENEURON'
        timestep: float = 0.025

    initialize: Initialization

    # Is this reasonable? (Is there an alternative?)
    def single_version_class(self):
        return globals()["Simulation"] 


class Simulation(SimulationParameterScanTemplate, SingleTypeMixin):
    """Only allows single float values and ensures nested attributes follow the same rule."""
    pass

    def generate_config(self):

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

        return self._sonata_config

