import uuid
from typing import Annotated, Literal

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
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

    Example:
        ion_channel_id: "abc123"
        variable_name: "gkbar_hh"
        section_list_modifications: {
            "somatic": 0.1,
            "axonal": [0.1, 0.2, 0.3],
        }
    """

    ion_channel_id: Annotated[uuid.UUID, Field(description="ID of the ion channel")]
    variable_name: str = Field(description="Name of the RANGE variable (e.g., 'gkbar_hh')")
    section_list_modifications: dict[str, float | list[float]] = Field(
        default_factory=dict,
        description="Modifications per section list (e.g., {'somatic': 0.1, 'axonal': 0.2})",
    )


class ByNeuronModification(OBIBaseModel):
    """Modify neuron level changes - GLOBAL and RANGE (in all SectionLists) variables of ion
    channels.

    Example (GLOBAL):
        ion_channel_id: uuid.UUID("...")
        channel_name: "StochKv3"
        variable_name: "vmin_StochKv3"
        variable_type: "GLOBAL"
        new_value: 0.5

    Example (RANGE):
        ion_channel_id: uuid.UUID("...")
        channel_name: "Ca_HVA2"
        variable_name: "gCa_HVAbar_Ca_HVA2"
        variable_type: "RANGE"
        new_value: 0.1
    """

    ion_channel_id: Annotated[uuid.UUID, Field(description="ID of the ion channel")]
    channel_name: Annotated[
        str,
        Field(
            min_length=1,
            description="Channel suffix (e.g., 'NaTg') used as key in conditions.mechanisms",
        ),
    ]
    variable_name: str = Field(
        description="Name of the variable (e.g., 'vmin_StochKv3' or 'gCa_HVAbar_Ca_HVA2')"
    )
    variable_type: Literal["RANGE", "GLOBAL"] = Field(
        default="GLOBAL",
        description="Variable type: 'RANGE' (section-specific) or 'GLOBAL' (neuron-wide)",
    )
    new_value: float | list[float] = Field(
        description="New value(s) that applies to entire neuron (GLOBAL) or all sections (RANGE)",
    )


class BySectionListNeuronalParameterModification(Block):
    """Modify RANGE variables of ion channels for specific section lists.

    This block allows modifying ion channel RANGE variables (e.g., conductances)
    with different values for different section lists (e.g., somatic, axonal).
    """

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        exclude=True,
        json_schema_extra={"ui_hidden": True},
    )

    modification: BySectionListModification = Field(
        title="RANGE Variable Modification",
        description="Ion channel RANGE variable modification by section list.",
        json_schema_extra={
            "ui_element": "ion_channel_range_variable_modification",
            "property_group": MappedPropertiesGroup.CIRCUIT,
            "property": CircuitMappedProperties.ION_CHANNEL_RANGE_VARIABLES,
        },
    )

    def config(self, _default_population_name: str, default_node_set: str) -> list[dict]:
        """Generate SONATA conditions.modifications entries for each section list.

        Returns:
            List of SONATA modification dicts, one per section list.
        """
        node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set, default_node_set)

        modifications = []
        for section_list, value in self.modification.section_list_modifications.items():
            if section_list == "all":
                modifications.append(
                    {
                        "name": f"modify_{self.modification.variable_name}_all",
                        "node_set": node_set,
                        "type": "configure_all_sections",
                        "section_configure": f"%s.{self.modification.variable_name} = {value}",
                    }
                )
                continue

            modifications.extend(
                {
                    "name": f"modify_{self.modification.variable_name}_{expanded_section_list}",
                    "node_set": node_set,
                    "type": "section_list",
                    "section_configure": (
                        f"{expanded_section_list}.{self.modification.variable_name} = {value}"
                    ),
                }
                for expanded_section_list in _expand_section_list(section_list)
            )

        return modifications


class ByNeuronNeuronalParameterModification(Block):
    """Modify ion channel variables (RANGE or GLOBAL) for specific neurons.

    This block handles both variable types:
    - RANGE variables (e.g., conductances like gCa_HVAbar_Ca_HVA2).
      Generates a single conditions.modifications entry using configure_all_sections.
    - GLOBAL variables apply uniformly to the entire neuron (e.g., reversal potentials).
      Generates a conditions.mechanisms entry keyed by channel name.
    """

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        exclude=True,
        json_schema_extra={"ui_hidden": True},
    )

    modification: ByNeuronModification = Field(
        title="Variable Modification",
        description="Ion channel variable modification (RANGE or GLOBAL).",
        json_schema_extra={
            "ui_element": "ion_channel_variable_modification",
            "property_group": MappedPropertiesGroup.CIRCUIT,
            "property": CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL,
        },
    )

    def config(self, _default_population_name: str, default_node_set: str) -> list[dict] | dict:
        """Generate SONATA config entry.

        Returns:
            For GLOBAL: dict {channel_name: {variable_name: new_value}} for conditions.mechanisms.
            For RANGE: list[dict] with a single conditions.modifications entry for all sections.
        """
        if self.modification.variable_type == "GLOBAL":
            return {
                self.modification.channel_name: {
                    self.modification.variable_name: self.modification.new_value
                }
            }

        node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set, default_node_set)
        return [
            {
                "name": f"modify_{self.modification.variable_name}_all",
                "node_set": node_set,
                "type": "configure_all_sections",
                "section_configure": (
                    f"%s.{self.modification.variable_name} = {self.modification.new_value}"
                ),
            }
        ]
