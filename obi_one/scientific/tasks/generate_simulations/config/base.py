import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar

import entitysdk
from libsonata import SimulatorType
from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.serialization_constants import (
    COORDINATE_CONFIG_FILENAME,
    SCAN_CONFIG_FILENAME,
)
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.exponential import ExponentialDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.ion_channel_model_circuit import CircuitFromIonChannelModels
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference
from obi_one.scientific.unions_and_references.neuron_sets import (
    BaseNeuronSetReference,
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.timestamps import TimestampsReference

SONATA_VERSION = 2.4

L = logging.getLogger(__name__)


DEFAULT_TIMESTAMPS_NAME = "Default: Simulation Start (0 ms)"
DEFAULT_DISTRIBUTION_NAME = "Default: Exponential, scale 50 ms"
DEFAULT_SPIKE_TIME_DISTRIBUTION_NAME = "Default: Normal, mean 5 ms, sd 1 ms"
DEFAULT_MORPHOLOGY_LOCATIONS_NAME = "Default: No Locations"

# Which reference type names a neuron set, given what the set contains. A default neuron set is
# built by the config rather than chosen by the user, so its reference type has to be derived
# rather than declared -- and the set already knows what it holds.
_NEURON_SET_REFERENCE_TYPES: dict[NeuronSetPopulationType, type[BaseNeuronSetReference]] = {
    NeuronSetPopulationType.BIOPHYSICAL: BiophysicalNeuronSetReference,
    NeuronSetPopulationType.POINT: PointNeuronSetReference,
    NeuronSetPopulationType.VIRTUAL: VirtualNeuronSetReference,
}


def build_neuron_set_reference(name: str, neuron_set: NeuronSet) -> BaseNeuronSetReference:
    """A resolved reference to a neuron set the config supplies rather than the user."""
    population_type = neuron_set.get_neuron_set_population_type()
    try:
        reference_type = _NEURON_SET_REFERENCE_TYPES[population_type]
    except KeyError as error:
        msg = (
            f"No reference type names a '{population_type}' neuron set, so "
            f"{type(neuron_set).__name__} cannot be used as a default."
        )
        raise OBIONEError(msg) from error

    reference = reference_type(block_dict_name="neuron_sets", block_name=name)
    neuron_set.set_block_name(name)
    reference.block = neuron_set
    return reference


def _build_resolved_reference(
    reference_type: type[BlockReference], block_dict_name: str, name: str, block: Block
) -> BlockReference:
    """A resolved reference to a block the config supplies rather than the user."""
    reference = reference_type(block_dict_name=block_dict_name, block_name=name)
    block.set_block_name(name)
    reference.block = block
    return reference


class BlockGroup(StrEnum):
    """Enumeration of block groups for simulation configuration."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    TARGETING_BLOCK_GROUP = "Targets"
    DISTRIBUTIONS_BLOCK_GROUP = "Distributions"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    CIRCUIT_MANIPULATIONS_GROUP = "Manipulations"
    EVENTS_GROUP = "Events"


class BaseSimulationScanConfig(InfoScanConfig, abc.ABC):
    """Abstract base class for simulation scan configurations."""

    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    _campaign: entitysdk.models.SimulationCampaign = None  # ty:ignore[possibly-missing-submodule]
    _sonata_version: ClassVar[float] = SONATA_VERSION
    _target_simulator: ClassVar[SimulatorType] = None
    _timestep: ClassVar[None] = None
    default_node_set_name: ClassVar[str] = "Default: All Biophysical Neurons"
    default_neuron_set_type: ClassVar[type[AllBiophysicalNeurons]] = AllBiophysicalNeurons

    # A neuron set reference left unset is filled in with the default for its own population
    # type, which may differ from the simulation-wide default. Every simulation config needs all
    # three, whatever its own default is: a point-only config can still hold a virtual set, and a
    # biophysical one can hold both.
    default_virtual_node_set_name: ClassVar[str] = "Default: All Virtual Neurons"
    default_point_node_set_name: ClassVar[str] = "Default: All Point Neurons"
    default_virtual_neuron_set_type: ClassVar[type[AllVirtualNeurons]] = AllVirtualNeurons
    default_point_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Publish the default names into the schema, so the UI never drifts from the code."""
        super().__init_subclass__(**kwargs)
        cls.model_config["json_schema_extra"].update(  # ty:ignore[unresolved-attribute]
            {
                SchemaKey.REFERENCE_TAG_DEFAULTS: {
                    tag: reference.block_name
                    for tag, reference in cls.default_block_references().items()
                }
            }
        )

    @classmethod
    def default_block_references(cls) -> dict[str, BlockReference]:
        """What each kind of unset block reference resolves to, keyed by its tag.

        Most roles resolve to whatever the simulation runs, which each family varies through
        ``default_neuron_set_type`` rather than by overriding this. A family that needs a role to
        mean something else overrides this method.

        Every role appears here, so the block each one names is also the source of the placeholder
        the UI shows for it -- ``__init_subclass__`` reads the names straight off these references
        and publishes them in the schema, which is why the two can never disagree. That in turn is
        why this is class-level and takes no circuit: the UI reads the schema without one.
        """
        simulation_neuron_set = build_neuron_set_reference(
            cls.default_node_set_name, cls.default_neuron_set_type()
        )
        return {
            ReferenceTag.SIMULATION_TARGET: simulation_neuron_set,
            ReferenceTag.STIMULUS_TARGET: simulation_neuron_set,
            ReferenceTag.SPIKE_REPLAY_SOURCE: simulation_neuron_set,
            ReferenceTag.SPIKE_REPLAY_TARGET: simulation_neuron_set,
            ReferenceTag.RECORDING_TARGET: simulation_neuron_set,
            ReferenceTag.SYNAPTIC_MANIPULATION_SOURCE: simulation_neuron_set,
            ReferenceTag.SYNAPTIC_MANIPULATION_TARGET: simulation_neuron_set,
            ReferenceTag.NEURONAL_MANIPULATION_TARGET: simulation_neuron_set,
            ReferenceTag.MORPHOLOGY_LOCATIONS_TARGET: simulation_neuron_set,
            # An unset operand of a combined neuron set means every neuron of that set's own
            # population type, which differs from the simulation default only when the combined
            # set is virtual or point.
            ReferenceTag.ANY_NEURON_SET_OPERAND: simulation_neuron_set,
            ReferenceTag.BIOPHYSICAL_NEURON_SET_OPERAND: simulation_neuron_set,
            ReferenceTag.NON_VIRTUAL_NEURON_SET_OPERAND: simulation_neuron_set,
            ReferenceTag.POINT_NEURON_SET_OPERAND: build_neuron_set_reference(
                cls.default_point_node_set_name, cls.default_point_neuron_set_type()
            ),
            ReferenceTag.VIRTUAL_NEURON_SET_OPERAND: build_neuron_set_reference(
                cls.default_virtual_node_set_name, cls.default_virtual_neuron_set_type()
            ),
            ReferenceTag.TIMESTAMPS: _build_resolved_reference(
                TimestampsReference,
                "timestamps",
                DEFAULT_TIMESTAMPS_NAME,
                SingleTimestamp(start_time=0.0),
            ),
            # Keying the two spike distributions by role rather than by reference type is what
            # lets them differ, which keyed by AllDistributionsReference they could not.
            ReferenceTag.INTER_SPIKE_INTERVAL_DISTRIBUTION: _build_resolved_reference(
                AllDistributionsReference,
                "distributions",
                DEFAULT_DISTRIBUTION_NAME,
                ExponentialDistribution(scale=50.0),
            ),
            ReferenceTag.SPIKE_TIME_DISTRIBUTION: _build_resolved_reference(
                AllDistributionsReference,
                "distributions",
                DEFAULT_SPIKE_TIME_DISTRIBUTION_NAME,
                NormalDistribution(mean=5.0, standard_deviation=1.0),
            ),
        }

    @property
    def simulation_node_set_name(self) -> str:
        """The SONATA node set the simulation runs.

        Only meaningful once references have been filled. A config that offers no target has no
        neuron sets dictionary either, so its node set is written from the default type directly.
        """
        if not hasattr(self.initialize, "node_set"):
            return self.default_node_set_name

        return resolve_neuron_set_ref_to_node_set(self.initialize.node_set)  # ty:ignore[invalid-argument-type]

    def check_simulation_target(self, circuit: Circuit) -> None:
        """Raise if the neuron set the simulation runs cannot actually be simulated.

        Virtual neurons only emit pre-determined spikes, so a simulation targeting them would have
        nothing to compute.
        """
        node_set = getattr(self.initialize, "node_set", None)
        if not isinstance(node_set, BaseNeuronSetReference):
            return

        if node_set.block.get_neuron_set_population_type() in {
            NeuronSetPopulationType.BIOPHYSICAL,
            NeuronSetPopulationType.POINT,
            NeuronSetPopulationType.NONVIRTUAL,
        }:
            return

        non_virtual_populations = Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_virtual=False,
            incl_point=True,
        )
        non_virtual_list = (
            ", ".join(f"'{pop}'" for pop in non_virtual_populations)
            if non_virtual_populations
            else "none found"
        )
        msg = (
            f"Simulation Neuron Set (Initialize -> Neuron Set): "
            f"'{node_set.block_name}' is virtual. "
            "Please use a non-virtual (biophysical or point) Neuron Set type. "
            f"Available non-virtual populations: {non_virtual_list}. "
            f"You may be able to reference one through an "
            f"MultiPopulationPredefinedNeuronSet block type. "
            "In future we will support population selection for any neuron set."
        )
        raise OBIONEError(msg)

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        simulation_length: (
            Annotated[
                NonNegativeFloat,
                Field(ge=MIN_SIMULATION_LENGTH_MILLISECONDS, le=MAX_SIMULATION_LENGTH_MILLISECONDS),
            ]
            | Annotated[
                list[
                    Annotated[
                        NonNegativeFloat,
                        Field(
                            ge=MIN_SIMULATION_LENGTH_MILLISECONDS,
                            le=MAX_SIMULATION_LENGTH_MILLISECONDS,
                        ),
                    ]
                ],
                Field(min_length=1),
            ]
        ) = Field(
            default=DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLISECONDS,
            },
        )

        v_init: float | list[float] = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLIVOLTS,
            },
        )
        random_seed: int | list[int] = Field(
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
            },
        )

    initialize: Initialize

    def base_sonata_config(self, sonata_config: dict | None = None) -> dict:
        """Returns the base SONATA configuration for the simulation campaign."""
        if sonata_config is None:
            sonata_config = {}

        sonata_config["version"] = self._sonata_version
        if self._target_simulator is None:
            msg = "Target simulator not specified for simulation campaign."
            raise NotImplementedError(msg)
        sonata_config["target_simulator"] = self._target_simulator.name

        sonata_config["run"] = {}
        sonata_config["run"]["dt"] = self.timestep
        sonata_config["run"]["random_seed"] = self.initialize.random_seed
        sonata_config["run"]["tstop"] = self.initialize.simulation_length

        sonata_config["conditions"] = {}
        sonata_config["conditions"]["v_init"] = self.initialize.v_init

        sonata_config["output"] = {}
        sonata_config["output"]["output_dir"] = "output"
        sonata_config["output"]["spikes_file"] = "spikes.h5"

        return sonata_config

    @property
    def target_simulator(self) -> SimulatorType:
        """The target simulator for the simulation campaign."""
        if self._target_simulator is None:
            msg = "Target simulator not specified for simulation campaign."
            raise NotImplementedError(msg)
        return self._target_simulator

    @property
    def timestep(self) -> PositiveFloat:
        """The simulation timestep."""
        if self._timestep is None:
            msg = "Timestep not specified for simulation campaign."
            raise NotImplementedError(msg)
        return self._timestep

    def entity_id_for_campaign_entity_generation(self) -> str:
        """Determines the entity ID for the simulation campaign based on the circuit."""
        if isinstance(self.initialize.circuit, list):  # ty:ignore[unresolved-attribute]
            if len(self.initialize.circuit) != 1:  # ty:ignore[unresolved-attribute]
                msg = "Only single circuit/MEModel currently supported for \
                    simulation campaign database persistence."
                raise OBIONEError(msg)
            return self.initialize.circuit[0].id_str  # ty:ignore[unresolved-attribute]
        if self.initialize.circuit is None:  # ty:ignore[unresolved-attribute]
            msg = "Circuit must be specified to determine entity ID for simulation campaign."
            raise OBIONEError(msg)
        try:
            return self.initialize.circuit.id_str  # ty:ignore[unresolved-attribute]
        except AttributeError as err:
            msg = "self.initialize.circuit must have an id_str attribute."
            raise OBIONEError(msg) from err

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> entitysdk.models.SimulationCampaign:  # ty:ignore[possibly-missing-submodule]
        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register SimulationCampaign Entity")

        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(  # ty:ignore[possibly-missing-submodule]
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=self.entity_id_for_campaign_entity_generation(),
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,  # ty:ignore[possibly-missing-submodule]
            file_path=output_root / SCAN_CONFIG_FILENAME,
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="campaign_generation_config",  # ty:ignore[invalid-argument-type]
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        simulations: list[entitysdk.models.Simulation],  # ty:ignore[possibly-missing-submodule]
        db_client: entitysdk.client.Client,
    ) -> None:  # ty:ignore[invalid-method-override]
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(  # ty:ignore[possibly-missing-submodule]
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )


class SimulationSingleConfigMixin(SingleConfigMixin):
    """Mixin for CircuitSimulationSingleConfig and MEModelSimulationSingleConfig.

    Inherits from SingleConfigMixin and overrides create_single_entity_with_config
    to register a Simulation entity instead of a generic TaskConfig.
    """

    def create_single_entity_with_config(
        self,
        campaign: entitysdk.models.SimulationCampaign,  # ty:ignore[possibly-missing-submodule]
        db_client: entitysdk.client.Client,
    ) -> entitysdk.models.Simulation:  # ty:ignore[possibly-missing-submodule]
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")

        if hasattr(self.initialize, "circuit"):  # ty:ignore[unresolved-attribute]
            circuit = self.initialize.circuit  # ty:ignore[unresolved-attribute]
        elif hasattr(self, "circuit"):
            circuit = self.circuit

        if not isinstance(
            circuit,
            (
                CircuitFromID,
                MEModelFromID,
                MEModelWithSynapsesCircuitFromID,
                CircuitFromIonChannelModels,
            ),
        ):
            msg = (
                "Simulation can only be saved to entitycore if circuit is CircuitFromID "
                "or MEModelFromID"
            )
            raise OBIONEError(msg)

        L.info("-- Register Simulation Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.Simulation(  # ty:ignore[possibly-missing-submodule]
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representation(),
                entity_id=self.entity_id_for_campaign_entity_generation(),  # ty:ignore[unresolved-attribute]
                simulation_campaign_id=campaign.id,
                number_neurons=-1,
            )
        )

        L.info("-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
            file_path=Path(self.coordinate_output_root, COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="simulation_generation_config",  # ty:ignore[invalid-argument-type]
        )
