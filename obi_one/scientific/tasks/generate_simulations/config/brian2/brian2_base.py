import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import Field, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.constants import (
    SIMULATION_TIMESTEP_MILLISECONDS,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
    BlockGroup,
)
from obi_one.scientific.unions.unions_recordings import (
    RecordingReference,
    RecordingUnion,
)


class Brian2SimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for Brian2-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.Brian2
    _timestep: ClassVar[PositiveFloat] = SIMULATION_TIMESTEP_MILLISECONDS

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

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass

    def base_sonata_config(self, sonata_config: dict | None = None) -> dict:
        """Returns the base SONATA configuration for the simulation campaign."""
        sonata_config = super().base_sonata_config(sonata_config)
        return sonata_config
