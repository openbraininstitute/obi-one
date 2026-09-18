"""Registry mapping each block `UIElement` to its validator.

This is the single source of truth the dispatcher in `tests/ui_schema/validate_block.py`
uses to route a block field to its validator. Adding a new block UI element means adding a
module in this package and a single entry here.
"""

from collections.abc import Callable

from obi_one.core.schema import UIElement

from .block_union import validate_block_union
from .boolean_input import validate_boolean_input
from .entity_property_dropdown import validate_entity_property_dropdown
from .float_optional import validate_float_optional
from .float_parameter_sweep import validate_float_param_sweep
from .int_parameter_sweep import validate_int_param_sweep
from .ion_channel_variable_modification_by_neuron import (
    validate_ion_channel_variable_modification_by_neuron,
)
from .ion_channel_variable_modification_by_section_list import (
    validate_ion_channel_variable_modification_by_section_list,
)
from .model_identifier import validate_model_identifier
from .model_identifier_multiple import validate_model_identifier_multiple
from .model_selector_single import validate_model_selector_single
from .morphology_location_selection import validate_morphology_location_selection
from .morphology_section_type_selection import validate_morphology_section_type_selection
from .neuron_ids import validate_neuron_ids
from .neuron_property_filter import validate_neuron_property_filter
from .neuron_set_combination import validate_neuron_set_combination
from .reference import validate_reference
from .select_efeatures_by_protocol import validate_select_efeatures_by_protocol
from .select_recordable_ion_channel_variable import (
    validate_select_recordable_ion_channel_variable,
)
from .string_constant import validate_string_constant
from .string_constant_enhanced import validate_string_constant_enhanced
from .string_input import validate_string_input
from .string_selection import validate_string_selection
from .string_selection_enhanced import validate_string_selection_enhanced
from .voltage_duration import validate_voltage_duration

# A block-element validator takes (schema, param, ref) and raises on failure.
BlockElementValidator = Callable[[dict, str, str], None]

# The single source of truth mapping each block UI element to its validator. Adding a new
# UI element means adding a module in this package and an entry here — nothing else.
VALIDATOR_BY_UI_ELEMENT: dict[UIElement, BlockElementValidator] = {
    UIElement.BLOCK_UNION: validate_block_union,
    UIElement.STRING_INPUT: validate_string_input,
    UIElement.BOOLEAN_INPUT: validate_boolean_input,
    UIElement.FLOAT_PARAMETER_SWEEP: validate_float_param_sweep,
    UIElement.INT_PARAMETER_SWEEP: validate_int_param_sweep,
    UIElement.FLOAT_OPTIONAL: validate_float_optional,
    UIElement.ENTITY_PROPERTY_DROPDOWN: validate_entity_property_dropdown,
    UIElement.REFERENCE: validate_reference,
    UIElement.NEURON_SET_COMBINATION: validate_neuron_set_combination,
    UIElement.STRING_SELECTION: validate_string_selection,
    UIElement.STRING_SELECTION_ENHANCED: validate_string_selection_enhanced,
    UIElement.STRING_CONSTANT: validate_string_constant,
    UIElement.STRING_CONSTANT_ENHANCED: validate_string_constant_enhanced,
    UIElement.NEURON_IDS: validate_neuron_ids,
    UIElement.MODEL_IDENTIFIER: validate_model_identifier,
    UIElement.MODEL_IDENTIFIER_MULTIPLE: validate_model_identifier_multiple,
    UIElement.MODEL_SELECTOR_SINGLE: validate_model_selector_single,
    UIElement.MORPHOLOGY_LOCATION_SELECTION: validate_morphology_location_selection,
    UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION: validate_morphology_section_type_selection,
    UIElement.ION_CHANNEL_VARIABLE_MODIFICATION_BY_SECTION_LIST: (
        validate_ion_channel_variable_modification_by_section_list
    ),
    UIElement.ION_CHANNEL_VARIABLE_MODIFICATION_BY_NEURON: (
        validate_ion_channel_variable_modification_by_neuron
    ),
    UIElement.SELECT_EFEATURES_BY_PROTOCOL: validate_select_efeatures_by_protocol,
    UIElement.SELECT_RECORDABLE_ION_CHANNEL_VARIABLE: (
        validate_select_recordable_ion_channel_variable
    ),
    UIElement.VOLTAGE_DURATION: validate_voltage_duration,
    UIElement.NEURON_PROPERTY_FILTER: validate_neuron_property_filter,
}
