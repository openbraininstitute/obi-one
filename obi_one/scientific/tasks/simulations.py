import abc
import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PrivateAttr,
)

from obi_one.core.block import Block
from obi_one.core.constants import (
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.blocks.neuron_sets import AllNeurons, NeuronSet
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
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
MEModelDiscriminator = Annotated[Circuit | MEModelFromID, Field(discriminator="type")]

DEFAULT_NODE_SET = "All"


class SimulationScanConfig(ScanConfig, abc.ABC):
    """Abstract base class for simulation scan configurations."""

    single_coord_class_name: ClassVar[str]
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    _campaign: entitysdk.models.SimulationCampaign = None

    @property
    def campaign(self) -> entitysdk.models.SimulationCampaign:
        if self._campaign is None:
            msg = "Campaign entity has not been created yet!"
            raise OBIONEError(msg)
        return self._campaign

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

    class Initialize(Block):
        circuit: None
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
            sonata_config["node_set"] = DEFAULT_NODE_SET

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

    info: Info = Field(
        title="Info",
        description="Information about the simulation campaign.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )

    def create_campaign_entity_with_config(
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
        if isinstance(self.initialize.circuit, (CircuitFromID, MEModelFromID)):
            entity_id = self.initialize.circuit.id_str
        elif isinstance(self.initialize.circuit, list):
            entity_id = self.initialize.circuit[0].id_str

        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=entity_id,
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

    def create_campaign_generation_entity(
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


class MEModelSimulationScanConfig(SimulationScanConfig):
    """MEModelSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Initialize(SimulationScanConfig.Initialize):
        circuit: MEModelDiscriminator | list[MEModelDiscriminator] = Field(
            title="ME Model", description="ME Model to simulate."
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )


ALL_NEURON_SET_NAME = "All Neurons"
ALL_NEURON_SET_BLOCK_REFERENCE = NeuronSetReference(
    block_dict_name="neuron_sets", block_name=ALL_NEURON_SET_NAME
)
DEFAULT_NEURON_SETS_DICTIONARY = {ALL_NEURON_SET_NAME: AllNeurons()}


class CircuitSimulationScanConfig(SimulationScanConfig):
    """CircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "CircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=lambda: DEFAULT_NEURON_SETS_DICTIONARY,
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

    class Initialize(SimulationScanConfig.Initialize):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit", description="Circuit to simulate."
        )
        node_set: Annotated[
            NeuronSetReference, Field(title="Neuron Set", description="Neuron set to simulate.")
        ]

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )


class SimulationSingleConfigMixin(abc.ABC):
    """Mixin for CircuitSimulationSingleConfig and MEModelSimulationSingleConfig."""

    _single_entity: entitysdk.models.Simulation

    @property
    def single_entity(self) -> entitysdk.models.Simulation:
        return self._single_entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client
    ) -> entitysdk.models.Simulation:
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")

        if not isinstance(self.initialize.circuit, (CircuitFromID, MEModelFromID)):
            msg = (
                "Simulation can only be saved to entitycore if circuit is CircuitFromID "
                "or MEModelFromID"
            )
            raise OBIONEError(msg)

        L.info("-- Register Simulation Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.Simulation(
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                entity_id=self.initialize.circuit.id_str,
                simulation_campaign_id=campaign.id,
            )
        )

        L.info("-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
            file_content_type="application/json",
            asset_label="simulation_generation_config",
        )


class CircuitSimulationSingleConfig(
    CircuitSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""


class MEModelSimulationSingleConfig(
    MEModelSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""


class GenerateSimulationTask(Task):
    config: CircuitSimulationSingleConfig | MEModelSimulationSingleConfig

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})

    def _add_sonata_simulation_config_inputs(self, circuit: Circuit) -> None:
        self._sonata_config["inputs"] = {}
        for stimulus in self.config.stimuli.values():
            self._ensure_block_neuron_set(stimulus)
            if hasattr(stimulus, "generate_spikes"):
                stimulus.generate_spikes(
                    circuit,
                    self.config.coordinate_output_root,
                    self.config.initialize.simulation_length,
                    source_node_population=circuit.default_population_name,
                )
            self._sonata_config["inputs"].update(
                stimulus.config(circuit, circuit.default_population_name)
            )

    def _add_sonata_simulation_config_reports(self, circuit: Circuit) -> None:
        self._sonata_config["reports"] = {}
        for recording in self.config.recordings.values():
            self._ensure_block_neuron_set(recording)
            self._sonata_config["reports"].update(
                recording.config(
                    circuit,
                    circuit.default_population_name,
                    self.config.initialize.simulation_length,
                )
            )

    def _add_sonata_simulation_config_manipulations(self) -> None:
        if hasattr(self.config, "synaptic_manipulations"):
            # Generate list of synaptic manipulation configs (executed in the order in the list)
            # TODO: Ensure that the order in the self.synaptic_manipulations dict is preserved!
            manipulation_list = [
                manipulation.config()
                for manipulation in self.config.synaptic_manipulations.values()
            ]
            if len(manipulation_list) > 0:
                self._sonata_config["connection_overrides"] = manipulation_list

    def _resolve_circuit(self, db_client: entitysdk.client.Client) -> Circuit:
        circuit = None
        if isinstance(self.config.initialize.circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            circuit = self.config.initialize.circuit
            self._sonata_config["network"] = self.config.initialize.circuit.path

        elif isinstance(self.config.initialize.circuit, CircuitFromID):
            L.info("initialize.circuit is a CircuitFromID instance.")

            for asset in self.config.initialize.circuit.entity(db_client=db_client).assets:
                if asset.label == "sonata_circuit":
                    circuit_dir = self.config.initialize.circuit.download_circuit_directory(
                        dest_dir=self.config.coordinate_output_root, db_client=db_client
                    )
                    circuit = Circuit(
                        name=self.config.initialize.circuit.entity(db_client=db_client).name,
                        path=str(circuit_dir / "circuit_config.json"),
                    )
                    self._sonata_config["network"] = asset.path + "/" + Path(circuit.path).name
                    break

        elif isinstance(self.config.initialize.circuit, MEModelFromID):
            L.info("initialize.circuit is a MEModelFromID instance.")
            self._circuit_id = self.config.initialize.circuit.id_str

            circuit = self.config.initialize.circuit.stage_memodel_as_circuit(
                db_client=db_client, dest_dir=self.config.coordinate_output_root
            )
            self._sonata_config["network"] = Path(circuit.path).name  # Correct?

        return circuit

    def _ensure_block_neuron_set(self, block: Block) -> None:
        """Ensure that any block with a missing neuron_set gets the default set, if applicable."""
        if hasattr(self.config, "neuron_sets") and getattr(block, "neuron_set", None) is None:
            block.neuron_set = self._default_neuron_set_ref()

    def _default_neuron_set_ref(self) -> NeuronSetReference:
        """Returns the reference for the default neuron set."""
        if ALL_NEURON_SET_BLOCK_REFERENCE.block_name not in self.config.neuron_sets:
            self.config.neuron_sets[ALL_NEURON_SET_BLOCK_REFERENCE.block_name] = AllNeurons()

        return ALL_NEURON_SET_BLOCK_REFERENCE

    def _ensure_simulation_target_neuron_set(self) -> None:
        """Ensure a neuron set exists matching `initialize.node_set`. Infer default if needed."""
        if self.initialize.node_set is None:
            L.info("initialize.node_set is None — setting default node set.")
            self.initialize.node_set = self._default_neuron_set_ref()

    def _resolve_neuron_sets(self, circuit: Circuit) -> None:
        # Resolve neuron sets and add them to the SONATA circuit object
        # NOTE: The name that is used as neuron_sets dict key is always used as name for a new node
        # set, even for a PredefinedNeuronSet in which case a new node set will be created
        # which just references the existing one. This is the most consistent behavior since
        # it will behave exactly the same no matter if random subsampling is used or not.
        # But this also means that existing names cannot be used as dict keys.

        if hasattr(self.config, "neuron_sets"):
            sonata_circuit = circuit.sonata_circuit

            self._ensure_simulation_target_neuron_set()

            for _name, _nset in self.config.neuron_sets.items():
                # Resolve node set based on current coordinate circuit's default node population
                # TODO: Better handling of (default) node population in case there is more than one
                # TODO: Inconsistency possible in case a node set definition would span multiple
                # populations. May consider force_resolve_ids=False to enforce resolving into given
                # population (but which won't be a human-readable representation any more)
                if _name != _nset.block_name:
                    msg = "Neuron set name mismatch!"
                    raise OBIONEError(msg)  # This should never happen if properly initialized

                if self.config.initialize.node_set.block.block_name == _name:
                    if self._sonata_config.get("node_set") is not None:
                        msg = "Node set config entry already defined!"
                        raise OBIONEError(msg)

                    # Assert that simulation neuron set is biophysical
                    if (
                        _nset.population_type(circuit, circuit.default_population_name)
                        != "biophysical"
                    ):
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
                self.config.coordinate_output_root,
                file_name=self.NODE_SETS_FILE_NAME,
                overwrite_if_exists=False,
            )
            self._sonata_config["node_sets_file"] = self.NODE_SETS_FILE_NAME

    def execute(self, db_client: entitysdk.client.Client = None) -> None:
        """Generates SONATA simulation config .json file."""
        # Initialize the SONATA simulation config
        self._sonata_config = self.config.initialize.initial_sonata_simulation_config()

        # Set circuit variable based on the type of initialize.circuit
        # circuit is used through-out generate rather than self.initialize.circuit
        circuit = self._resolve_circuit(db_client)

        self._sonata_config["output"] = {"output_dir": "output", "spikes_file": "spikes.h5"}
        self._sonata_config["conditions"]["mechanisms"] = {
            "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
        }

        self._add_sonata_simulation_config_inputs(circuit)
        self._add_sonata_simulation_config_reports(circuit)
        self._add_sonata_simulation_config_manipulations()
        self._resolve_neuron_sets(circuit)

        # Write simulation config file (.json)
        simulation_config_path = Path(self.config.coordinate_output_root) / self.CONFIG_FILE_NAME
        with simulation_config_path.open("w", encoding="utf-8") as f:
            json.dump(self._sonata_config, f, indent=2)

        if db_client:
            self.save_generated_simulation_assets_to_entity(db_client)

    def save_generated_simulation_assets_to_entity(
        self, db_client: entitysdk.client.Client
    ) -> None:
        L.info("-- Upload sonata_simulation_config")
        _ = db_client.upload_file(
            entity_id=self.config.single_entity.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.config.coordinate_output_root, "simulation_config.json"),
            file_content_type="application/json",
            asset_label="sonata_simulation_config",
        )

        L.info("-- Upload custom_node_sets")
        _ = db_client.upload_file(
            entity_id=self.config.single_entity.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.config.coordinate_output_root, "node_sets.json"),
            file_content_type="application/json",
            asset_label="custom_node_sets",
        )

        L.info("-- Upload spike replay files")
        for input_ in self._sonata_config["inputs"]:
            if "spike_file" in list(self._sonata_config["inputs"][input_]):
                spike_file = self._sonata_config["inputs"][input_]["spike_file"]
                if spike_file is not None:
                    _ = db_client.upload_file(
                        entity_id=self.config.single_entity.id,
                        entity_type=entitysdk.models.Simulation,
                        file_path=Path(self.config.coordinate_output_root, spike_file),
                        file_content_type="application/x-hdf5",
                        asset_label="replay_spikes",
                    )
