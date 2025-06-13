import json
import os
from typing import ClassVar, Literal, Self

from pydantic import Field, PrivateAttr, model_validator

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.info import Info
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.scientific.circuit.neuron_sets import NeuronSet
from obi_one.scientific.unions.unions_extracellular_location_sets import (
    ExtracellularLocationSetUnion,
)
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion, NeuronSetReference
from obi_one.scientific.unions.unions_recordings import RecordingUnion, RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusUnion, StimulusReference
from obi_one.scientific.unions.unions_synapse_set import SynapseSetUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsUnion, TimestampsReference

from obi_one.database.reconstruction_morphology_from_id import ReconstructionMorphologyFromID

import entitysdk

class SimulationsForm(Form):
    """Simulations Form."""

    single_coord_class_name: ClassVar[str] = "Simulation"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    timestamps: dict[str, TimestampsUnion] = Field(default_factory=dict, reference_type=TimestampsReference.__name__, description="Timestamps for the simulation")
    stimuli: dict[str, StimulusUnion] = Field(default_factory=dict, reference_type=StimulusReference.__name__, description="Stimuli for the simulation")
    recordings: dict[str, RecordingUnion] = Field(default_factory=dict, reference_type=RecordingReference.__name__, description="Recordings for the simulation")
    neuron_sets: dict[str, NeuronSetUnion] = Field(default_factory=dict, reference_type=NeuronSetReference.__name__, description="Neuron sets for the simulation")

    # synapse_sets: dict[str, SynapseSetUnion]
    # intracellular_location_sets: dict[str, MorphologyLocationUnion]
    # extracellular_location_sets: dict[str, ExtracellularLocationSetUnion]

    class Initialize(Block):
        circuit: list[Circuit] | Circuit | ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID]
        simulation_length: list[float] | float = 100.0
        node_set: NeuronSetReference = Field(default=None, description="Simulation initialization parameters")
        random_seed: list[int] | int = 1
        extracellular_calcium_concentration: list[float] | float = 1.1
        v_init: list[float] | float = -80.0
        
        spike_location: Literal["AIS", "soma"] | list[Literal["AIS", "soma"]] = "soma"
        sonata_version: list[int] | int = 1
        target_simulator: list[str] | str = "CORENEURON"
        timestep: list[float] | float = Field(default=0.025, description="Simulation time step in ms")

    initialize: Initialize
    info: Info

    
    def add(self, block: Block, name:str='') -> None:

        block_dict_name = self.block_mapping[block.__class__.__name__]["block_dict_name"]
        reference_type_name = self.block_mapping[block.__class__.__name__]["reference_type"]

        if name in self.__dict__.get(block_dict_name).keys():
            raise ValueError(f"Block with name '{name}' already exists in '{block_dict_name}'!")
        
        else: 
            reference_type = globals()[reference_type_name]
            ref = reference_type(block_dict_name=block_dict_name, block_name=name)
            block.set_ref(ref)
            self.__dict__[block_dict_name][name] = block


    def set(self, block: Block, name: str = '') :
        """Sets a block in the form."""
        self.__dict__[name] = block


    
    # Below are initializations of the individual components as part of a simulation
    # by setting their simulation_level_name as the one used in the simulation form/GUI
    # TODO: Ensure in GUI that these names don't have spaces or special characters
    @model_validator(mode="after")
    def initialize_timestamps(self) -> Self:
        """Initializes timestamps within simulation campaign."""
        for _k, _v in self.timestamps.items():
            _v.set_simulation_level_name(_k)
        return self

    @model_validator(mode="after")
    def initialize_stimuli(self) -> Self:
        """Initializes stimuli within simulation campaign."""
        for _k, _v in self.stimuli.items():
            _v.set_simulation_level_name(_k)
        return self

    @model_validator(mode="after")
    def initialize_recordings(self) -> Self:
        """Initializes recordings within simulation campaign."""
        for _k, _v in self.recordings.items():
            _v.set_simulation_level_name(_k)
        return self

    @model_validator(mode="after")
    def initialize_neuron_sets(self) -> Self:
        """Initializes neuron sets within simulation campaign."""
        for _k, _v in self.neuron_sets.items():
            _v.set_simulation_level_name(_k)
        return self


class Simulation(SimulationsForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})

    def _resolve_neuron_set_dictionary(self, neuron_set):
        """Resolves a neuron set based on current coordinate circuit's default node population and \
            returns its dictionary.
        """
        nset_def = neuron_set.get_node_set_definition(
            self.initialize.circuit, self.initialize.circuit.default_population_name
        )
        # FIXME: Better handling of (default) node population in case there is more than one
        # FIXME: Inconsistency possible in case a node set definition would span multiple populations
        #        May consider force_resolve_ids=False to enforce resolving into given population
        #        (but which won't be a human-readable representation any more)
        name = neuron_set.name
        dictionary = {name: nset_def}
        return name, dictionary

    def generate(self, db_client: entitysdk.client.Client = None):
        """Generates SONATA simulation config .json file."""
        self._sonata_config = {}
        self._sonata_config["version"] = self.initialize.sonata_version
        self._sonata_config["target_simulator"] = self.initialize.target_simulator

        self._sonata_config["network"] = self.initialize.circuit.path

        self._sonata_config["run"] = {}
        self._sonata_config["run"]["dt"] = self.initialize.timestep
        self._sonata_config["run"]["random_seed"] = self.initialize.random_seed
        self._sonata_config["run"]["tstop"] = self.initialize.simulation_length

        self._sonata_config["conditions"] = {}
        self._sonata_config["conditions"]["extracellular_calcium"] = (
            self.initialize.extracellular_calcium_concentration
        )
        self._sonata_config["conditions"]["v_init"] = self.initialize.v_init
        self._sonata_config["conditions"]["spike_location"] = self.initialize.spike_location

        self._sonata_config["conditions"]["mechanisms"] = {
            "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
        }

        # Generate stimulus input configs
        self._sonata_config["inputs"] = {}
        for stimulus_key, stimulus in self.stimuli.items():
            if hasattr (stimulus, "generate_spikes"):
                stimulus.generate_spikes(self.initialize.circuit, self.initialize.circuit.default_population_name, self.coordinate_output_root)
            self._sonata_config["inputs"].update(stimulus.config())

        # Generate recording configs
        self._sonata_config["reports"] = {}
        for recording_key, recording in self.recordings.items():
            self._sonata_config["reports"].update(recording.config())

        # Resolve neuron sets and add them to the SONATA circuit object
        # NOTE: The name that is used as neuron_sets dict key is always used as name for a new node
        # set, even for a PredefinedNeuronSet in which case a new node set will be created which just
        # references the existing one. This is the most consistent behavior since it will behave
        # exactly the same no matter if random subsampling is used or not. But this also means that
        # existing names cannot be used as dict keys.
        os.makedirs(self.coordinate_output_root, exist_ok=True)
        c = self.initialize.circuit.sonata_circuit
        for _name, _nset in self.neuron_sets.items():
            # Resolve node set based on current coordinate circuit's default node population
            # FIXME: Better handling of (default) node population in case there is more than one
            # FIXME: Inconsistency possible in case a node set definition would span multiple populations
            #        May consider force_resolve_ids=False to enforce resolving into given population
            #        (but which won't be a human-readable representation any more)
            assert _name == _nset.name, (
                "Neuron set name mismatch!"
            )  # This should never happen if properly initialized

            if self.initialize.node_set.block.name == _name:
                assert self._sonata_config.get("node_set") is None, (
                    "Node set config entry already defined!"
                )
                self._sonata_config["node_set"] = _name

            # Add node set to SONATA circuit object
            # (will raise an error in case already existing)
            nset_def = _nset.get_node_set_definition(
                self.initialize.circuit, self.initialize.circuit.default_population_name
            )
            NeuronSet.add_node_set_to_circuit(c, {_name: nset_def}, overwrite_if_exists=False)

        # Write node sets from SONATA circuit object to .json file
        # (will raise an error if file already exists)
        NeuronSet.write_circuit_node_set_file(
            c,
            self.coordinate_output_root,
            file_name=self.NODE_SETS_FILE_NAME,
            overwrite_if_exists=False,
        )
        self._sonata_config["node_sets_file"] = self.NODE_SETS_FILE_NAME

        # Write simulation config file (.json)
        simulation_config_path = os.path.join(self.coordinate_output_root, self.CONFIG_FILE_NAME)
        with open(simulation_config_path, "w") as f:
            json.dump(self._sonata_config, f, indent=2)
