import logging
from enum import StrEnum
from typing import ClassVar

from obi_one.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromIDFromID
from obi_one.scientific.from_id.electrical_recording_from_id import ElectricalRecordingFromID
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerReference,
    SynapticModelAssignerUnion,
)
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    NeuronSetUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    SYNAPSE_PARAMETERS = "Synapse parameters"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit components"


class EModelOptimizationScanConfig(InfoScanConfig, SingleConfigMixin):
    name: ClassVar[str] = "E-Model Optimization"
    description: ClassVar[str] = "Fill description"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP],
    }

    class Initialize(Block):
        morphology: CellMorphologyFromIDFromID | list[CellMorphologyFromIDFromID] = Field(
            title="Morphology",
            description="Morphology description.",
        )

        ephys_traces: ElectricalRecordingFromID | tuple[ElectricalRecordingFromID] = Field(
            title="Electrical Recordings",
            description="Electrical recordings description.",
        )

        seed: int | list[int] = Field(
            title="Random Seed",
            description="Random seed for optimization.",
        )

        """
        OTHER OPTIMIZATION PARAMETERS, E.G. OPTIMIZATION ALGORITHM, NUMBER OF GENERATIONS, POPULATION SIZE, ETC.
        """

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    morphology_locations: dict[str, SectionListMorphologyLocationsUnion] = Field(
        # default_factory=dict,
        # description="Synaptic models for synapse parameterization.",
        # json_schema_extra={
        #     SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
        #     SchemaKey.REFERENCE_TYPE: SynapticModelReference.__name__,
        #     SchemaKey.SINGULAR_NAME: "Synaptic Model",
        #     SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
        #     SchemaKey.GROUP_ORDER: 1,
        # },
    )

    ion_channel_models_with_constraints_by_location: dict[IonChannelModelsWithConstraintsByLocationUnion] = Field(
        default_factory=dict,
        title="Ion Channel Models with Constraints by Location",
        description="Ion channel models with constraints by location.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            # SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Ion Channel Models with Constraints for Location",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    neuronal_manipulations: dict[str, NeuronalManipulationUnion] = Field(
        default_factory=dict,
        title="Neuronal Manipulations",
        description="Neuronal manipulations for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: NeuronalManipulationReference.__name__,
            SchemaKey.SINGULAR_NAME: "Neuronal Manipulation",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class EModelOptimizationSingleConfig(EModelOptimizationScanConfig, SingleConfigMixin):
    pass
