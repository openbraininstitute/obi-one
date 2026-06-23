import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import Field, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    PointNeuronSetReference,
)
class LearningEngineSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for learning engine-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.LearningEngine
    _timestep: ClassVar[PositiveFloat] = 0.1
    default_node_set_name: ClassVar[str] = "Default: All Point Neurons"

    def default_neuron_set_reference(self) -> PointNeuronSetReference:
        """Returns the default neuron set reference for the simulation."""
        return PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )

    class Initialize(BaseSimulationScanConfig.Initialize):
        random_seed: int | list[int] = Field(
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
                SchemaKey.UI_HIDDEN: True,
            },
        )
