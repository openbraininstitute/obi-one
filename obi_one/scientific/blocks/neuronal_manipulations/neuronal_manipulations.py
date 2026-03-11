import uuid
from typing import Annotated, ClassVar

import entitysdk
from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.emodel_parameters import _expand_section_list, neuron_variable_name
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


class ByNeuronModification(OBIBaseModel):
    """Modify neuron level changes - GLOBAL and RANGE (in all SectionLists) variables of ion
    channels and built-in section properties.

    Example (GLOBAL ion channel):
        ion_channel_id: uuid.UUID("...")
        channel_name: "StochKv3"
        variable_name: "vmin_StochKv3"
        variable_type: "GLOBAL"
        new_value: 0.5

    Example (RANGE ion channel):
        ion_channel_id: uuid.UUID("...")
        channel_name: "Ca_HVA2"
        variable_name: "gCa_HVAbar_Ca_HVA2"
        variable_type: "RANGE"
        new_value: 0.1

    Example (section property):
        variable_name: "cm"
        variable_type: "RANGE"
        new_value: 1.0
    """

    ion_channel_id: Annotated[uuid.UUID, Field(description="ID of the ion channel")] | None = None
    channel_name: (
        Annotated[
            str,
            Field(
                min_length=1,
                description="Channel suffix (e.g., 'NaTg') used as key in conditions.mechanisms",
            ),
        ]
        | None
    ) = None
    variable_name: str = Field(
        description="Name of the variable (e.g., 'vmin_StochKv3', 'gCa_HVAbar_Ca_HVA2', 'cm', 'Ra')"
    )
    new_value: float | list[float] = Field(
        description="New value(s) that applies to entire neuron (GLOBAL) or all sections (RANGE)",
    )

    def variable_type(self, db_client: entitysdk.client.Client | None = None) -> str:
        """Determine variable type (RANGE or GLOBAL) based on ion channel model metadata."""
        if db_client is None:
            # TODO: what should be the behavior when we do not have the client?
            return "RANGE"

        model = db_client.get_entity(
            entity_id=self.ion_channel_id,
            entity_type=entitysdk.models.ion_channel_model.IonChannelModel,
        )

        if model.neuron_block.range is not None:
            range_variables = [
                neuron_variable_name(var_name, model.nmodl_suffix)
                for entry in model.neuron_block.range
                for var_name in entry
            ]
            if self.variable_name in range_variables:
                return "RANGE"
        if model.neuron_block.global_ is not None:
            global_variables = [
                neuron_variable_name(var_name, model.nmodl_suffix)
                for entry in model.neuron_block.global_
                for var_name in entry
            ]
            if self.variable_name in global_variables:
                return "GLOBAL"

        msg = (
            f"Variable {self.variable_name} not found in RANGE or GLOBAL entries "
            f"of neuron block metadata for ion channel {model.name}"
        )
        raise OBIONEError(msg)


class BySectionListMechanismVariableNeuronalManipulation(Block):
    """Set values for an ion channel variable in each section list where the ion channel exists.


    Example section lists: axonal, apical, basal and somatic.


    These correspond to `section lists` in the NEURON simulator nomenclature:
    https://nrn.readthedocs.io/en/latest/progref/modelspec/programmatic/topology/seclist.html#sectionlist.
    """

    title: ClassVar[str] = "Variable Modification by Section List"

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        exclude=True,
        json_schema_extra={"ui_hidden": True},
    )

    modification: BySectionListModification = Field(
        title="Ion channel variable manipulations by section type",
        description="Ion channel RANGE variable modification by section list.",
        json_schema_extra={
            "ui_element": "ion_channel_variable_modification_by_section_list",
            "property_group": MappedPropertiesGroup.CIRCUIT,
            "property": CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL,
        },
    )

    def config(
        self,
        _default_population_name: str,
        default_node_set: str,
        db_client: entitysdk.client.Client | None,  # noqa: ARG002
    ) -> list[dict]:
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


class ByNeuronMechanismVariableNeuronalManipulation(Block):
    """Modify a variable of an ion channel wherever the ion channel is present in the neuron."""

    title: ClassVar[str] = "Full Neuron Variable Modification"

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        exclude=True,
        json_schema_extra={"ui_hidden": True},
    )

    modification: ByNeuronModification = Field(
        title="Ion channel variable manipulations by neuron",
        description="Ion channel variable modification (RANGE or GLOBAL) by neuron.",
        json_schema_extra={
            "ui_element": "ion_channel_variable_modification_by_neuron",
            "property_group": MappedPropertiesGroup.CIRCUIT,
            "property": CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL,
        },
    )

    def config(
        self,
        _default_population_name: str,
        default_node_set: str,
        db_client: entitysdk.client.Client | None,
    ) -> list[dict] | dict:
        """Generate SONATA config entry.

        Returns:
            For GLOBAL ion channel: dict {channel_name: {variable_name: new_value}}
            for conditions.mechanisms.
            For RANGE ion channel: list[dict] with a single conditions.modifications
            entry for all sections.
            For section properties (cm, Ra): list[dict] with a single
            conditions.modifications entry for all sections.
        """
        # Handle RANGE variables (including section properties)
        variable_type = self.modification.variable_type(db_client)
        if variable_type == "RANGE":
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

        # Handle ion channel variables (existing logic)
        if variable_type == "GLOBAL":
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
