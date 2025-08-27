import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

import entitysdk
from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PrivateAttr,
    model_validator,
)

from obi_one.core.block import Block
from obi_one.core.constants import (
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.core.exception import OBIONEError
from obi_one.core.form import Form
from obi_one.core.info import Info
from obi_one.core.single import SingleCoordinateMixin
from obi_one.database.circuit_from_id import CircuitFromID
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.scientific.circuit.neuron_sets import NeuronSet
from obi_one.scientific.unions.unions_manipulations import (
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference, RecordingUnion
from obi_one.scientific.unions.unions_stimuli import StimulusReference, StimulusUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsReference, TimestampsUnion

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    CIRUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    EVENTS_GROUP = "Events"
    CIRCUIT_MANIPULATIONS_GROUP = "Circuit Manipulations"


CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]


class SimulationsForm(Form):
    """Simulations Form."""

    single_coord_class_name: ClassVar[str] = "Simulation"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "block_block_group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
                BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
                BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
                BlockGroup.EVENTS_GROUP,
                BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            ]
        }

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        reference_type=TimestampsReference.__name__,
        description="Timestamps for the simulation.",
        singular_name="Timestamps",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )
    stimuli: dict[str, StimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        reference_type=StimulusReference.__name__,
        description="Stimuli for the simulation.",
        singular_name="Stimulus",
        group=BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
        group_order=0,
    )
    recordings: dict[str, RecordingUnion] = Field(
        default_factory=dict,
        reference_type=RecordingReference.__name__,
        description="Recordings for the simulation.",
        singular_name="Recording",
        group=BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
        group_order=1,
    )
    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        reference_type=NeuronSetReference.__name__,
        description="Neuron sets for the simulation.",
        singular_name="Neuron Set",
        group=BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
        group_order=0,
    )
    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        default_factory=dict,
        reference_type=SynapticManipulationsReference.__name__,
        description="Synaptic manipulations for the simulation.",
        singular_name="Synaptic Manipulation",
        group=BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
        group_order=1,
    )

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator]
        node_set: Annotated[
            NeuronSetReference, Field(title="Neuron Set", description="Neuron set to simulate.")
        ]
        simulation_length: (
            Annotated[
                NonNegativeFloat,
                Field(
                    ge=_MIN_SIMULATION_LENGTH_MILLISECONDS, le=_MAX_SIMULATION_LENGTH_MILLISECONDS
                ),
            ]
            | Annotated[
                list[
                    Annotated[
                        NonNegativeFloat,
                        Field(
                            ge=_MIN_SIMULATION_LENGTH_MILLISECONDS,
                            le=_MAX_SIMULATION_LENGTH_MILLISECONDS,
                        ),
                    ]
                ],
                Field(min_length=1),
            ]
        ) = Field(
            default=1000.0,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            units="ms",
        )
        extracellular_calcium_concentration: list[NonNegativeFloat] | NonNegativeFloat = Field(
            default=1.1,
            title="Extracellular Calcium Concentration",
            description=(
                "Extracellular calcium concentration around the synapse in millimoles (mM). "
                "Increasing this value increases the probability of synaptic vesicle release, "
                "which in turn increases the level of network activity. In vivo values are "
                "estimated to be ~0.9-1.2mM, whilst in vitro values are on the order of 2mM."
            ),
            units="mM",
        )
        v_init: list[float] | float = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            units="mV",
        )
        random_seed: list[int] | int = Field(
            default=1, description="Random seed for the simulation."
        )

        _spike_location: Literal["AIS", "soma"] | list[Literal["AIS", "soma"]] = PrivateAttr(
            default="soma"
        )
        _sonata_version: list[NonNegativeFloat] | NonNegativeFloat = PrivateAttr(default=2.4)
        _target_simulator: (
            Literal["NEURON", "CORENEURON"] | list[Literal["NEURON", "CORENEURON"]]
        ) = PrivateAttr(default="NEURON")  # Target simulator for the simulation
        _timestep: list[PositiveFloat] | PositiveFloat = PrivateAttr(
            default=0.025
        )  # Simulation time step in ms

        def initial_sonata_simulation_config(self) -> dict:
            """Returns the default SONATA conditions dictionary."""
            sonata_config = {}
            sonata_config["version"] = self._sonata_version
            sonata_config["target_simulator"] = self._target_simulator

            sonata_config["run"] = {}
            sonata_config["run"]["dt"] = self._timestep
            sonata_config["run"]["random_seed"] = self.random_seed
            sonata_config["run"]["tstop"] = self.simulation_length

            sonata_config["conditions"] = {}
            sonata_config["conditions"]["extracellular_calcium"] = (
                self.extracellular_calcium_concentration
            )
            sonata_config["conditions"]["v_init"] = self.v_init
            sonata_config["conditions"]["spike_location"] = self._spike_location

            return sonata_config

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )
    info: Info = Field(
        title="Info",
        description="Information about the simulation campaign.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )

    def initialize_db_campaign(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.SimulationCampaign:
        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register SimulationCampaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=self.initialize.circuit.id_str
                if isinstance(self.initialize.circuit, CircuitFromID)
                else self.initialize.circuit[0].id_str,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,
            file_path=output_root / "run_scan_config.json",
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def save(
        self, simulations: list[entitysdk.models.Simulation], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )

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

    @model_validator(mode="after")
    def initialize_synaptic_manipulations(self) -> Self:
        """Initializes manipulationms within simulation campaign."""
        for _k, _v in self.synaptic_manipulations.items():
            _v.set_simulation_level_name(_k)
        return self


class Simulation(SimulationsForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})

    def _add_sonata_simulation_config_inputs(self, circuit: Circuit) -> None:
        self._sonata_config["inputs"] = {}
        for stimulus in self.stimuli.values():
            if hasattr(stimulus, "generate_spikes"):
                stimulus.generate_spikes(
                    circuit,
                    self.coordinate_output_root,
                    self.initialize.simulation_length,
                    source_node_population=circuit.default_population_name,
                )
            self._sonata_config["inputs"].update(
                stimulus.config(circuit, circuit.default_population_name)
            )

    def _add_sonata_simulation_config_reports(self, circuit: Circuit) -> None:
        self._sonata_config["reports"] = {}
        for recording in self.recordings.values():
            self._sonata_config["reports"].update(
                recording.config(
                    circuit, circuit.default_population_name, self.initialize.simulation_length
                )
            )

    def _add_sonata_simulation_config_manipulations(self) -> None:
        # Generate list of synaptic manipulation configs (executed in the order in the list)
        # TODO: Ensure that the order in the self.synaptic_manipulations dict is preserved!
        manipulation_list = [
            manipulation.config() for manipulation in self.synaptic_manipulations.values()
        ]
        if len(manipulation_list) > 0:
            self._sonata_config["connection_overrides"] = manipulation_list

    def generate(self, db_client: entitysdk.client.Client = None) -> None:
        """Generates SONATA simulation config .json file."""
        # Initialize the SONATA simulation config
        self._sonata_config = self.initialize.initial_sonata_simulation_config()

        # Set circuit variable based on the type of initialize.circuit
        # circuit is used through-out generate rather than self.initialize.circuit
        circuit = None
        if isinstance(self.initialize.circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            circuit = self.initialize.circuit
            self._sonata_config["network"] = self.initialize.circuit.path

        if isinstance(self.initialize.circuit, CircuitFromID):
            L.info("initialize.circuit is a CircuitFromID instance.")
            self._circuit_id = self.initialize.circuit.id_str

            for asset in self.initialize.circuit.entity(db_client=db_client).assets:
                if asset.label == "sonata_circuit":
                    self.initialize.circuit.download_circuit_directory(
                        dest_dir=self.coordinate_output_root, db_client=db_client
                    )
                    circuit = Circuit(
                        name=self.initialize.circuit.entity(db_client=db_client).name,
                        path=str(self.coordinate_output_root / asset.path / "circuit_config.json"),
                    )
                    self._sonata_config["network"] = asset.path + "/" + Path(circuit.path).name
                    break

        self._sonata_config["output"] = {"output_dir": "output", "spikes_file": "spikes.h5"}
        self._sonata_config["conditions"]["mechanisms"] = {
            "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
        }

        # Add stimulus inputs to sonata simulation config
        self._add_sonata_simulation_config_inputs(circuit)

        # Add recordings to sonata simulation config
        self._add_sonata_simulation_config_reports(circuit)

        # Add synaptic manipulations to sonata simulation config
        self._add_sonata_simulation_config_manipulations()

        # Resolve neuron sets and add them to the SONATA circuit object
        # NOTE: The name that is used as neuron_sets dict key is always used as name for a new node
        # set, even for a PredefinedNeuronSet in which case a new node set will be created
        # which just references the existing one. This is the most consistent behavior since
        # it will behave exactly the same no matter if random subsampling is used or not.
        # But this also means that existing names cannot be used as dict keys.
        Path(self.coordinate_output_root).mkdir(parents=True, exist_ok=True)

        sonata_circuit = circuit.sonata_circuit
        for _name, _nset in self.neuron_sets.items():
            # Resolve node set based on current coordinate circuit's default node population
            # TODO: Better handling of (default) node population in case there is more than one
            # TODO: Inconsistency possible in case a node set definition would span multiple
            # populations. May consider force_resolve_ids=False to enforce resolving into given
            # population (but which won't be a human-readable representation any more)
            if _name != _nset.name:
                msg = "Neuron set name mismatch!"
                raise OBIONEError(msg)  # This should never happen if properly initialized

            if self.initialize.node_set.block.name == _name:
                if self._sonata_config.get("node_set") is not None:
                    msg = "Node set config entry already defined!"
                    raise OBIONEError(msg)

                # Assert that simulation neuron set is biophysical
                if _nset.population_type(circuit, circuit.default_population_name) != "biophysical":
                    msg = f"Simulation Neuron Set (Initialize -> Neuron Set): '{_name}' "
                    "is not biophysical!"
                    raise OBIONEError(msg)

                self._sonata_config["node_set"] = _name

            # Add node set to SONATA circuit object
            # (will raise an error in case already existing)
            nset_def = _nset.get_node_set_definition(
                circuit, circuit.default_population_name, force_resolve_ids=True
            )
            NeuronSet.add_node_set_to_circuit(
                sonata_circuit, {_name: nset_def}, overwrite_if_exists=False
            )

        # Write node sets from SONATA circuit object to .json file
        # (will raise an error if file already exists)
        NeuronSet.write_circuit_node_set_file(
            sonata_circuit,
            self.coordinate_output_root,
            file_name=self.NODE_SETS_FILE_NAME,
            overwrite_if_exists=False,
        )
        self._sonata_config["node_sets_file"] = self.NODE_SETS_FILE_NAME

        # Write simulation config file (.json)
        simulation_config_path = Path(self.coordinate_output_root) / self.CONFIG_FILE_NAME
        with simulation_config_path.open("w", encoding="utf-8") as f:
            json.dump(self._sonata_config, f, indent=2)

    def save(
        self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client
    ) -> None:
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")

        L.info("-- Register Simulation Entity")
        simulation = db_client.register_entity(
            entitysdk.models.Simulation(
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                entity_id=self._circuit_id,
                simulation_campaign_id=campaign.id,
            )
        )

        L.info("-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
            file_content_type="application/json",
            asset_label="simulation_generation_config",
        )

        L.info("-- Upload sonata_simulation_config")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "simulation_config.json"),
            file_content_type="application/json",
            asset_label="sonata_simulation_config",
        )

        L.info("-- Upload custom_node_sets")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "node_sets.json"),
            file_content_type="application/json",
            asset_label="custom_node_sets",
        )

        L.info("-- Upload spike replay files")
        for input_ in self._sonata_config["inputs"]:
            if "spike_file" in list(self._sonata_config["inputs"][input_]):
                spike_file = self._sonata_config["inputs"][input_]["spike_file"]
                if spike_file is not None:
                    _ = db_client.upload_file(
                        entity_id=simulation.id,
                        entity_type=entitysdk.models.Simulation,
                        file_path=Path(self.coordinate_output_root, spike_file),
                        file_content_type="application/x-hdf5",
                        asset_label="replay_spikes",
                    )

        return simulation
