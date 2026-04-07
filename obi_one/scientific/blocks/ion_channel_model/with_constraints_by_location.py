import uuid
from typing import Annotated, ClassVar, Literal

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.ion_channel_model import (
    IonChannelModelWithConductance,
    IonChannelModelWithMaxPermeability,
    IonChannelModelWithoutConductance
)
from obi_one.scientific.library.emodel_parameters import _expand_section_list
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)


class BySectionListModification(OBIBaseModel):
    """Modification for RANGE variables by section list.

    Example (ion channel):
        ion_channel_id: "abc123"
        variable_name: "gkbar_hh"
        section_list_modifications: {
            "somatic": 0.1,
            "axonal": [0.1, 0.2, 0.3],
        }

    Example (section property):
        variable_name: "cm"
        section_list_modifications: {
            "somatic": 1.0,
            "apical": 2.0,
        }
    """

    ion_channel_id: Annotated[uuid.UUID, Field(description="ID of the ion channel")] | None = None
    variable_name: str = Field(
        description="Name of the RANGE variable (e.g., 'gkbar_hh', 'cm', 'Ra')"
    )
    section_list_modifications: dict[str, float | list[float]] = Field(
        default_factory=dict,
        description="Modifications per section list (e.g., {'somatic': 0.1, 'axonal': 0.2})",
    )

