import abc
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.tasks.generate_simulations.config.base.base import (
    BaseSimulationScanConfig,
)

MEModelDiscriminator = Annotated[MEModelCircuit | MEModelFromID, Field(discriminator="type")]


class MEModelBaseSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Circuit-specific simulation scan config (blocks, fields, and Initialize)."""

    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Initialize(BaseSimulationScanConfig.Initialize, abc.ABC):
        """Important to define the circuit here, even if overriden,
        so that it keeps its position in the schema.
        """

        circuit: MEModelDiscriminator | list[MEModelDiscriminator] = Field(
            title="ME Model",
            description="ME Model to simulate.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
        )
