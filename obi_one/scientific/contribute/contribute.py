import json
import os
from typing import ClassVar, Literal, Self, Annotated

from pydantic import Field, PrivateAttr, model_validator, NonNegativeInt, NonNegativeFloat, PositiveInt, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.constants import _MIN_SIMULATION_LENGTH_MILLISECONDS, _MAX_SIMULATION_LENGTH_MILLISECONDS
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.info import Info
#from obi_one.core.exception import OBIONE_Error
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.scientific.circuit.neuron_sets import NeuronSet
from obi_one.scientific.unions.unions_extracellular_location_sets import (
    ExtracellularLocationSetUnion,
)
from obi_one.scientific.unions.unions_manipulations import SynapticManipulationsUnion, SynapticManipulationsReference
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion
from obi_one.scientific.unions.unions_neuron_sets import SimulationNeuronSetUnion, NeuronSetReference
from obi_one.scientific.unions.unions_recordings import RecordingUnion, RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusUnion, StimulusReference
from obi_one.scientific.unions.unions_synapse_set import SynapseSetUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsUnion, TimestampsReference

from obi_one.database.circuit_from_id import CircuitFromID

import entitysdk
from collections import OrderedDict

from datetime import UTC, datetime

from pathlib import Path

import logging
import uuid
L = logging.getLogger(__name__)

from enum import StrEnum
class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"  
    ASSET_BLOCK_GROUP = "Morphology files"
    CONTRIBUTOR_BLOCK_GROUP = "Experimenter"
    STRAIN_BLOCK_GROUP = "Animal strain"
    LOCATION_GROUP = "Location"
    PROTOCOL_GROUP = "Protocol"
    LICENSE_GROUP = "License"

from pydantic import BaseModel
from enum import Enum, StrEnum, auto
from datetime import timedelta
from typing import TypedDict, Optional

class Sex(StrEnum):
    male = auto()
    female = auto()
    unknown = auto()

class AgePeriod(StrEnum):
    prenatal = auto()
    postnatal = auto()
    unknown = auto()

class StatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"
    pending = "pending"

class Contribution(BaseModel):
    name: str = Field(default="", description="Contribution name")
    status: StatusEnum = Field(default=StatusEnum.pending, description="Status")

class Author(BaseModel):
    given_name: Optional[str] = None
    family_name: Optional[str] = None


class Reference(BaseModel):
    type: str = Field(..., description="Reference type (e.g. DOI, PubMed)")
    identifier: str = Field(..., description="Unique reference identifier")

    class Config:
        json_schema_extra = {
            "title": "Reference"
        }

class Publication(Block):
    name: str = Field(default="", description="Publication name")
    description: str = Field(default="", description="Publication description")
    DOI: Optional[str] = Field(default="")
    publication_title: Optional[str] = Field(default="")
    authors: Optional[Author] = Field(default=None)
    publication_year: Optional[int] = Field(default=None)
    abstract: Optional[str] = Field(default="")
  #  reference: Optional[Reference] = Field(default=None)

    class Config:
        json_schema_extra = {
            "title": "Publication"
        }

class MTypeClassification(Block):
    mtype_class_id: uuid.UUID | None = Field(default=None, description="UUID for MType classification")


class ContributeMorphologyForm(Form):
    """Contribute Morphology Form."""

    single_coord_class_name: ClassVar[str] = "ContributeMorphology"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"
    
    class Config:
        json_schema_extra = {
            "block_block_group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
                BlockGroup.ASSET_BLOCK_GROUP,
                BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
                BlockGroup.STRAIN_BLOCK_GROUP,
                BlockGroup.LOCATION_GROUP,
                BlockGroup.PROTOCOL_GROUP,
                BlockGroup.LICENSE_GROUP
            ]
        }
        #arbitrary_types_allowed = True  # Add this line
   
    class Assets(Block):
        swc_file: str | None = Field(default=None, description="SWC file for the morphology.")
        asc_file: str | None = Field(default=None, description="ASC file for the morphology.")
        h5_file: str | None = Field(default=None, description="H5 file for the morphology.")

#    class MTypeClassification:
#        mtype_class_id: uuid.UUID | None = Field(default=None)


  
    class ReconstructionMorphology(Block):
 #       model_config = ConfigDict(from_attributes=True)
 #       location: PointLocationBase | None
 #       legacy_id: list[str] | None
    #    mtypes: uuid.UUID#MTypeClassification | None

        name: str = Field(default="", description="Name of the morphology")  # Add default
        description: str = Field(default="", description="Description")     # Add default
        species_id: uuid.UUID | None = Field(default=None)                  # Make nullable with default
        strain_id: uuid.UUID | None = Field(default=None)
        brain_region_id: uuid.UUID | None = Field(default=None)             # Make nullable
        legacy_id: list[str] | None = Field(default=None)


    class Subject(Block):
        name: str = Field(default="", description="Subject name")
        description: str = Field(default="", description="Subject description")
        sex: Annotated[Sex, Field(title="Sex", description="Sex of the subject")] = Sex.unknown
        weight: Optional[float] = Field(
        default=None,
        title="Weight",
        description="Weight in grams",
        gt=0.0,
        json_schema_extra={"default": None}  # Ensure default appears in schema
        )
        age_value: Optional[timedelta] = Field(default=None, title="Age value", description="Age value interval.", gt=timedelta(0))
        age_min: Optional[timedelta] = Field(default=None, title="Minimum age range", description="Minimum age range", gt=timedelta(0))
        age_max: Optional[timedelta] = Field(default=None, title="Maximum age range", description="Maximum age range", gt=timedelta(0))
        age_period: AgePeriod | None = AgePeriod.unknown

        model_config = {"extra": "forbid"}

    class License(Block):       
        license_id: uuid.UUID | None = Field(default=None)

    class ScientificArtifact(Block):
        #model_config = ConfigDict(from_attributes=True)
        #published_in: str | None = None
        experiment_date: datetime | None = Field(default=None)
        contact_email: str | None = Field(default=None)
        atlas_id: uuid.UUID | None = Field(default=None)

        #    mtype: MTypeClassification = Field(title="Classification", description="Upload morphology swc, asc, and h5.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=2)
 
    assets: Assets = Field(
            default_factory=Assets,  
            title="Assets", 
            description="Morphology files.", 
            group=BlockGroup.SETUP_BLOCK_GROUP, 
            group_order=0
        )
    
    contribution: Contribution = Field(
        default_factory=Contribution,  # ✅ Add this
        title="Contribution", 
        description="Contributor.", 
        group=BlockGroup.SETUP_BLOCK_GROUP, 
        group_order=1
        )
    
    morphology: ReconstructionMorphology = Field(
        default_factory=ReconstructionMorphology,  # ✅ Add this
        title="Morphology", 
        description="Information about contributors.", 
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP, 
        group_order=0
        )
    
    subject: Subject = Field(
        default_factory=Subject,  # ✅ Add this
        title="Subject", 
        description="Information about the subject.", 
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP, 
        group_order=0
        )
    
    
    publication: Publication = Field(
        default_factory=Publication,
        title="Publication Details",
        description="Publication details.",
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP,
        group_order=0
    )

    license: License = Field(
        default_factory=License,  # ✅ Add this
        title="License", 
        description="The license used.", 
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP, 
        group_order=0
        )
    
    scientificartifact: ScientificArtifact = Field(
        default_factory=ScientificArtifact,  # ✅ Add this
        title="Scientific Artifact", 
        description="Information about the artifact.", 
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP, 
        group_order=0
        )
    
    mtype: MTypeClassification = Field(
        default_factory=MTypeClassification,  # ✅ Add this
        title="Mtype Classification", 
        description="The mtype.", 
        group=BlockGroup.CONTRIBUTOR_BLOCK_GROUP, 
        group_order=0
        )

    def initialize_db_campaign(self, output_root: Path, multiple_value_parameters_dictionary={}, db_client: entitysdk.client.Client=None):

        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")

        L.info(f"-- Register SimulationCampaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=self.initialize.circuit.id_str if isinstance(self.initialize.circuit, CircuitFromID) else self.initialize.circuit[0].id_str,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info(f"-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,
            file_path=output_root / "run_scan_config.json",
            file_content_type="application/json",
            asset_label='campaign_generation_config'
        )

        # L.info(f"-- Upload campaign_summary")
        # _ = db_client.upload_file(
        #     entity_id=self._campaign.id,
        #     entity_type=entitysdk.models.SimulationCampaign,
        #     file_path=Path(output_root, "bbp_workflow_campaign_config.json"),
        #     file_content_type="application/json",
        #     asset_label='campaign_summary'
        # )

        return self._campaign
    
    def save(self, simulations, db_client: entitysdk.client.Client) -> None:

        L.info("3. Saving completed simulation campaign generation")

        L.info(f"-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )

        return None

    
    def add(self, block: Block, name:str='') -> None:

        block_dict_name = self.block_mapping[block.__class__.__name__]["block_dict_name"]
        reference_type_name = self.block_mapping[block.__class__.__name__]["reference_type"]

        if name in self.__dict__.get(block_dict_name).keys():
            raise OBIONE_Error(f"Block with name '{name}' already exists in '{block_dict_name}'!")
        
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

    @model_validator(mode="after")
    def initialize_synaptic_manipulations(self) -> Self:
        """Initializes manipulationms within simulation campaign."""
        for _k, _v in self.synaptic_manipulations.items():
            _v.set_simulation_level_name(_k)
        return self


# def _resolve_neuron_set_dictionary(neuron_set, _circuit):
#         """Resolves a neuron set based on current coordinate circuit's default node population and \
#             returns its dictionary.
#         """
#         nset_def = neuron_set.get_node_set_definition(
#             _circuit, _circuit.default_population_name
#         )
#         # FIXME: Better handling of (default) node population in case there is more than one
#         # FIXME: Inconsistency possible in case a node set definition would span multiple populations
#         #        May consider force_resolve_ids=False to enforce resolving into given population
#         #        (but which won't be a human-readable representation any more)
#         name = neuron_set.name
#         dictionary = {name: nset_def}
#         return name, dictionary


class ContributeMorphology(ContributeMorphologyForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})

    def generate(self, db_client: entitysdk.client.Client = None):
        """Generates SONATA simulation config .json file."""

        # Set _circuit parameter based on the type of initialize.circuit
        # _circuit is used through-out generate rather than self.initialize.circuit
        _circuit = None
        if isinstance(self.initialize.circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            _circuit = self.initialize.circuit
            self._sonata_config["network"] = self.initialize.circuit.path

        if isinstance(self.initialize.circuit, CircuitFromID):
            L.info("initialize.circuit is a CircuitFromID instance.")
            self._circuit_id = self.initialize.circuit.id_str

            for asset in self.initialize.circuit.entity(db_client=db_client).assets:
                if asset.label == "sonata_circuit":
                    self.initialize.circuit.download_circuit_directory(dest_dir=self.coordinate_output_root, db_client=db_client)
                    _circuit = Circuit(name=self.initialize.circuit.entity(db_client=db_client).name, path=str(self.coordinate_output_root / asset.path / "circuit_config.json"))
                    self._sonata_config["network"] = asset.path + "/" + Path(_circuit.path).name
                    break


        self._sonata_config["output"] = {
            "output_dir": "output",
            "spikes_file": "spikes.h5"
        }

        self._sonata_config["version"] = self.initialize._sonata_version
        self._sonata_config["target_simulator"] = self.initialize._target_simulator

        self._sonata_config["run"] = {}
        self._sonata_config["run"]["dt"] = self.initialize._timestep
        self._sonata_config["run"]["random_seed"] = self.initialize.random_seed
        self._sonata_config["run"]["tstop"] = self.initialize.simulation_length

        self._sonata_config["conditions"] = {}
        self._sonata_config["conditions"]["extracellular_calcium"] = (
            self.initialize.extracellular_calcium_concentration
        )
        self._sonata_config["conditions"]["v_init"] = self.initialize.v_init
        self._sonata_config["conditions"]["spike_location"] = self.initialize._spike_location

        self._sonata_config["conditions"]["mechanisms"] = {
            "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
        }

        # Generate stimulus input configs
        self._sonata_config["inputs"] = {}
        for stimulus_key, stimulus in self.stimuli.items():
            if hasattr (stimulus, "generate_spikes"):
                stimulus.generate_spikes(_circuit, self.coordinate_output_root, self.initialize.simulation_length, source_node_population=_circuit.default_population_name)
            self._sonata_config["inputs"].update(stimulus.config(_circuit, _circuit.default_population_name))
            # 

        # Generate recording configs
        self._sonata_config["reports"] = {}
        for recording_key, recording in self.recordings.items():
            self._sonata_config["reports"].update(recording.config(_circuit, _circuit.default_population_name, self.initialize.simulation_length))

        # Generate list of synaptic manipulation configs (executed in the order in the list)
        # FIXME: Check and make sure that the order in the self.synaptic_manipulations dict is preserved!
        manipulation_list = []
        for manipulation_key, manipulation in self.synaptic_manipulations.items():
            manipulation_list.append(manipulation.config())
        if len(manipulation_list) > 0:
            self._sonata_config["connection_overrides"] = manipulation_list

        # Resolve neuron sets and time to the SONATA circuit object
        # NOTE: The name that is used as neuron_sets dict key is always used as name for a new node
        # set, even for a PredefinedNeuronSet in which case a new node set will be created which just
        # references the existing one. This is the most consistent behavior since it will behave
        # exactly the same no matter if random subsampling is used or not. But this also means that
        # existing names cannot be used as dict keys.
        os.makedirs(self.coordinate_output_root, exist_ok=True)
        c = _circuit.sonata_circuit
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

                # Assert that simulation neuron set is biophysical
                if _nset.population_type(_circuit, _circuit.default_population_name) != "biophysical":
                    raise OBIONE_Error(
                        f"Simulation Neuron Set (Initialize -> Neuron Set): '{_name}' is not biophysical!"
                    )

                self._sonata_config["node_set"] = _name

            # Add node set to SONATA circuit object
            # (will raise an error in case already existing)
            nset_def = _nset.get_node_set_definition(
                _circuit, _circuit.default_population_name, force_resolve_ids=True
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


    def save(self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client) -> None:
        """Saves the simulation to the database."""
        
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")
        
        L.info(f"-- Register Simulation Entity")
        simulation = db_client.register_entity(
            entitysdk.models.Simulation(
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                entity_id=self._circuit_id,
                simulation_campaign_id=campaign.id,
                
            )
        )

        L.info(f"-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
            file_content_type="application/json",
            asset_label='simulation_generation_config'
        )

        L.info(f"-- Upload sonata_simulation_config")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "simulation_config.json"),
            file_content_type="application/json",
            asset_label='sonata_simulation_config'
        )
        
        L.info(f"-- Upload custom_node_sets")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "node_sets.json"),
            file_content_type="application/json",
            asset_label='custom_node_sets'
        )

        L.info(f"-- Upload spike replay files")
        for input in self._sonata_config["inputs"]:
            if "spike_file" in list(self._sonata_config["inputs"][input]):
                spike_file = self._sonata_config["inputs"][input]["spike_file"]
                if spike_file is not None:
                    _ = db_client.upload_file(
                        entity_id=simulation.id,
                        entity_type=entitysdk.models.Simulation,
                        file_path=Path(self.coordinate_output_root, spike_file),
                        file_content_type="application/x-hdf5",
                        asset_label='replay_spikes'
                    )

        return simulation
