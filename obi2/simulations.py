from .template import Template, SubTemplate, SingleTypeMixin
from .stimulus import Stimulus
from .circuit_grouping import CircuitGrouping
from .timestamps import Timestamps
from .recording import Recording
from .circuit import Circuit

class SimulationCampaignTemplate(Template):
    """Base simulation model that contains a generic nested object."""
    circuit_groupings: dict[str, CircuitGrouping]
    timestamps: dict[str, Timestamps]
    stimuli: dict[str, Stimulus]
    recordings: dict[str, Recording]

    class Initialization(SubTemplate):
        circuit: Circuit
        simulation_length: float = 100.0
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


class Simulation(SimulationCampaignTemplate, SingleTypeMixin):
    """Only allows single float values and ensures nested attributes follow the same rule."""
    pass
