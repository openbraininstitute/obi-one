from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_recordings import (
    RecordingReference,
    RecordingUnion,
)


class NeuronSimulationScanConfig(SimulationScanConfig):
    """Abstract base class for neuron-based simulation scan configurations."""

    recordings: dict[str, RecordingUnion] = Field(
        default_factory=dict,
        description="Recordings for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: RecordingReference.__name__,
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class NeuronSimulationSingleConfig(SimulationSingleConfigMixin):
    """Mixin for neuron-based single simulation configurations."""
