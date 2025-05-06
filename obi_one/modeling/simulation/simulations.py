from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin

from obi_one.modeling.unions.unions_timestamps import TimestampsUnion
from obi_one.modeling.unions.unions_recordings import RecordingUnion
from obi_one.modeling.unions.unions_stimuli import StimulusUnion
from obi_one.modeling.unions.unions_synapse_set import SynapseSetUnion
from obi_one.modeling.unions.unions_neuron_sets import NeuronSetUnion
from obi_one.modeling.unions.unions_intracellular_location_sets import IntracellularLocationSetUnion
from obi_one.modeling.unions.unions_extracellular_location_sets import ExtracellularLocationSetUnion

from obi_one.modeling.circuit.circuit import Circuit
from obi_one.modeling.circuit.neuron_sets import NeuronSet

import json
import os

from pydantic import PrivateAttr, Field, model_validator
from typing import ClassVar
from typing_extensions import Self

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
        node_set: NeuronSetUnion  # NOTE: Must be member of the neuron_sets dict!
        random_seed: list[int] | int = 1
        extracellular_calcium_concentration: list[float] | float = 1.1
        v_init: list[float] | float = -80.0

        sonata_version: list[int] | int = 1
        target_simulator: list[str] | str = "CORENEURON"
        timestep: list[float] | float = 0.025

    initialize: Initialize

    @model_validator(mode="after")
    def check_node_set(self) -> Self:
        """Checks that given node set is member of the neuron_sets dict."""
        assert self.initialize.node_set.name in self.neuron_sets, "Node set must be within neuron sets dictionary!"
        assert self.initialize.node_set == self.neuron_sets[self.initialize.node_set.name], "Node set inconsistency!"
        return self

class Simulation(SimulationsForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""
    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"
    USE_NAME_SUFFIX: ClassVar[bool] = True

    _sonata_config: dict = PrivateAttr(default={})

    def _resolve_neuron_set(self, neuron_set, circuit, population):
        """Resolves neuron set based on current coordinate's circuit."""
        if len(self.single_coordinate_scan_params.scan_params) > 0 and self.USE_NAME_SUFFIX:
            # Use coordinate-specific suffix to distinguish between different instances
            # which may have the same name but will be resolved differently
            coord_suffix = f"__coord_{self.idx}"
        else:
            # Suffix disabled, or no suffix required in case there is only a single simulation
            coord_suffix = ""

        nset_def = neuron_set.get_node_set_definition(circuit, population)
        # FIXME: Inconsistency possible in case a node set definition would span multiple populations
        #        May consider force_resolve_ids=False to enforce resolving into given population
        #        (but which won't be a human-readable representation any more)
        if nset_def is None:
            # Neuron set already existing, nothing to add
            name = neuron_set.node_set  # Use name of actual (existing) node set
            expression = None
        else:
            # New expression needs to be added using a new name
            name = neuron_set.name + coord_suffix
            expression = {name: nset_def}
        return name, expression

    def generate(self):
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
        self._sonata_config["conditions"]["extracellular_calcium"] = self.initialize.extracellular_calcium_concentration
        self._sonata_config["conditions"]["v_init"] = self.initialize.v_init

        self._sonata_config["conditions"]["mechanisms"] = {
            "ProbAMPANMDA_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            },
            "ProbGABAAB_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            }
        }

        self._sonata_config["reports"] = {}
        for recording_key, recording in self.recordings.items():
            self._sonata_config["reports"][recording_key] = recording.generate_config()        

        # Write SONATA node sets file (.json)
        os.makedirs(self.coordinate_output_root, exist_ok=True)
        c = self.initialize.circuit.sonata_circuit
        for _name, _nset in self.neuron_sets.items():
            # Resolve node set based on current coordinate circuit's default node population
            # FIXME: Better handling of (default) node population in case there is more than one
            nset_name, nset_expression = self._resolve_neuron_set(_nset, self.initialize.circuit, self.initialize.circuit.default_population_name)
            if self.initialize.node_set.name == _name:
                assert self._sonata_config.get("node_set") is None, "Node set config entry already defined!"
                self._sonata_config["node_set"] = nset_name
            if nset_expression is None:
                # Node set already existing, no need to add
                pass
            else:
                # Add node set to SONATA circuit object
                # (will raise an error in case already existing)
                NeuronSet.add_node_set_to_circuit(c, nset_expression, overwrite_if_exists=False)
        # Write node sets from SONATA circuit object to .json file
        # (will raise an error if file already exists)
        NeuronSet.write_circuit_node_set_file(c, self.coordinate_output_root, file_name=self.NODE_SETS_FILE_NAME, overwrite_if_exists=False)
        self._sonata_config["node_sets_file"] = self.NODE_SETS_FILE_NAME

        # Write simulation config file (.json)
        simulation_config_path = os.path.join(self.coordinate_output_root, self.CONFIG_FILE_NAME)
        with open(simulation_config_path, "w") as f:
            json.dump(self._sonata_config, f, indent=2)
