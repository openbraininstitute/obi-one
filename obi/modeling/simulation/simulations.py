from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin

from obi.modeling.unions.unions_timestamps import TimestampsUnion
from obi.modeling.unions.unions_recordings import RecordingUnion
from obi.modeling.unions.unions_stimuli import StimulusUnion
from obi.modeling.unions.unions_synapse_set import SynapseSetUnion
from obi.modeling.unions.unions_neuron_sets import NeuronSetUnion
from obi.modeling.unions.unions_intracellular_location_sets import IntracellularLocationSetUnion
from obi.modeling.unions.unions_extracellular_location_sets import ExtracellularLocationSetUnion

from obi.modeling.circuit.circuit import Circuit

import json
import os

from pydantic import PrivateAttr, Field, model_validator
from typing import ClassVar
from typing_extensions import Self

# NOTE: With CustomDict (below), deserialization won't work. Also, it breaks the GUI.
#
# from typing import Any
# from pydantic_core import CoreSchema, core_schema
# from pydantic import GetCoreSchemaHandler, TypeAdapter
#
# class CustomDict(dict):
#     @classmethod
#     def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
#         return core_schema.no_info_after_validator_function(cls, handler(dict))
#
#     @staticmethod
#     def _set_key_as_name(obj, key):
#         pass
#         # if hasattr(obj, "name"):
#         #     if obj.name is None:
#         #         obj.name = key
#         #     else:
#         #         assert obj.name == key, "Name mismatch!"
#
#     def __init__(self, *args, **kwargs):
#         # print(f"INIT: {args}, {kwargs}")
#         for arg in args:
#             assert isinstance(arg, dict), "Dict expected!"
#             for _k, _v in arg.items():
#                 self._set_key_as_name(_v, _k)
#         for _k, _v in kwargs.items():
#             self._set_key_as_name(_v, _k)
#         self.update(*args, **kwargs)
#
#     def __setitem__(self, key, value):
#         # print(f"ITEM SET: {key}: {value}")
#         self._set_key_as_name(value, key)
#         return dict.__setitem__(self, key, value)


class SimulationsForm(Form):
    """
    """

    _single_coord_class_name: str = "Simulation"

    timestamps: dict[str, TimestampsUnion] = Field(description="Timestamps for the simulation")
    stimuli: dict[str, StimulusUnion]
    recordings: dict[str, RecordingUnion]
    neuron_sets: dict[str, NeuronSetUnion]
    synapse_sets: dict[str, SynapseSetUnion]
    intracellular_location_sets: dict[str, IntracellularLocationSetUnion]
    extracellular_location_sets: dict[str, ExtracellularLocationSetUnion]

    class Initialize(Block):
        circuit: list[Circuit] | Circuit
        simulation_length: list[float] | float = 100.0
        node_set: NeuronSetUnion  # NOTE: Needs to be member of the neuron_sets dict!
        # node_set: str  # NOTE: Needs to be member of the neuron_sets dict  [FIXME: Neuron set not selectable in GUI]
        random_seed: list[int] | int = 1
        extracellular_calcium_concentration: list[float] | float = 1.1
        v_init: list[float] | float = -80.0

        sonata_version: list[int] | int = 1
        target_simulator: list[str] | str = 'CORENEURON'
        timestep: list[float] | float = 0.025

    initialize: Initialize

    # @staticmethod
    # def find_key(dictionary, value):
    #     """Finds the key of a dict corresponding to a given value, if any."""
    #     for _k, _v in dictionary.items():
    #         if _v is value:
    #             return _k
    #     return None

    # FIXME: Won't de-serialize with this check enabled!!
    # @model_validator(mode='after')
    # def check_node_set(self) -> Self:
    #     """Checks if given node set is member of the neuron_sets dict."""
    #     assert self.find_key(self.neuron_sets, self.initialize.node_set) is not None, "Node set must be member of neuron sets dictionary!"
    #     return self
    @model_validator(mode='after')
    def check_node_set(self) -> Self:
        """Checks that given node set is member of the neuron_sets dict."""
        assert self.initialize.node_set.name in self.neuron_sets, "Node set must be within of neuron sets dictionary!"
        assert self.initialize.node_set == self.neuron_sets[self.initialize.node_set.name], "Node set inconsistency!"
        return self

class Simulation(SimulationsForm, SingleCoordinateMixin):
    """Only allows single float values and ensures nested attributes follow the same rule."""
    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})

    def generate(self):

        # Define a coordinate suffix to be used in node set names in order
        # to avoid confusion since node sets may resolve to different sets
        # of neurons in different coordinate instances
        if len(self.single_coordinate_scan_params.scan_params) > 0:
            coord_suffix = f"__coord_{self.idx}"
        else:
            coord_suffix = ""

        self._sonata_config = {}
        self._sonata_config['version'] = self.initialize.sonata_version
        self._sonata_config['target_simulator'] = self.initialize.target_simulator

        self._sonata_config['network'] = self.initialize.circuit.path
        self._sonata_config['node_set'] = self.initialize.node_set.name + coord_suffix
        # self._sonata_config['node_set'] = self.find_key(self.neuron_sets, self.initialize.node_set)
        self._sonata_config['node_sets_file'] = self.NODE_SETS_FILE_NAME

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

        # Write SONATA node sets file (.json)
        os.makedirs(self.coordinate_output_root, exist_ok=True)
        for _name, _nset in self.neuron_sets:
            # Resolve node set based on current coordinate circuit's default node population
            # FIXME: Better handling of default node population in case of more than one
            nset_def = _nset.get_node_set_definition(self.initialize.circuit, self.initialize.circuit.default_population_name)
            if nset_def is None:
                # Exisint node set, nothing to add
                pass
            else:
                # Node set needs to be added to circuit's node sets
                # TODO

        # Write simulation config file (.json)
        simulation_config_path = os.path.join(self.coordinate_output_root, self.CONFIG_FILE_NAME)
        with open(simulation_config_path, 'w') as f:
            json.dump(self._sonata_config, f, indent=2)
