from typing import ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_manipulations.base import (
    InterNeuronSetSynapticManipulation,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)


class ScaleAcetylcholineUSESynapticManipulation(InterNeuronSetSynapticManipulation):
    """Removed in #1205; kept so that saved configs using it still load."""

    title: ClassVar[str] = (
        "Demo: scale U_SE to modulate acetylcholine effect on synaptic release probability"
        " (deprecated)"
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_DEPRECATED_BLOCKS,
            SchemaKey.FALSE_MESSAGE: "This manipulation is deprecated and should not be used.",
        },
    }

    use_scaling: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.7050728631217412,
        title="Scale U_SE (ACh)",
        description="Scale the U_SE (ACh) parameter of the Tsodyks-Markram synaptic model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def config(self, default_node_set: str = "All") -> dict:  # ruff: ignore[unused-method-argument]
        msg = (
            f"{self.__class__.__name__} is deprecated: it reset earlier weight changes on the same"
            " synapses. Remove it from the configuration."
        )
        raise ConfigValidationError(msg)
