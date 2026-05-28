import logging
from typing import ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.generate_simulations.config.base.base import (
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.base.me_model import (
    MEModelBaseSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_base import (
    NeuronSimulationScanConfig,
)
from obi_one.scientific.unions.unions_neuronal_manipulations import (
    NeuronalManipulationReference,
    NeuronalManipulationUnion,
)
from obi_one.scientific.unions.unions_stimuli import (
    MEModelStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
)

L = logging.getLogger(__name__)


class MEModelSimulationScanConfig(NeuronSimulationScanConfig, MEModelBaseSimulationScanConfig):
    """MEModelSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Initialize(
        NeuronSimulationScanConfig.Initialize, MEModelBaseSimulationScanConfig.Initialize
    ):
        pass

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    stimuli: dict[str, MEModelStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: StimulusReference.__name__,
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
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

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
    }


class MEModelSimulationSingleConfig(MEModelSimulationScanConfig, SimulationSingleConfigMixin):
    """Only allows single values."""
