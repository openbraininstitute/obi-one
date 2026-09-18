"""Registries mapping each `UIElement` to its validator.

Two dicts, one per dispatch context:

- `VALIDATOR_BY_UI_ELEMENT` — block elements (a field inside a block). Used by
  `validate_block_elements` in `tests/ui_schema/validate_block.py`.
- `ROOT_VALIDATOR_BY_UI_ELEMENT` — root elements (a top-level slot that renders a whole
  block). Used by `validate_root_element` in `tests/ui_schema/validators/root/config.py`.

These are the single source of truth for validator dispatch. Adding a new UI element means
adding a module in the relevant package and a single entry in the matching dict here.
"""

from collections.abc import Callable

from obi_one.core.schema import UIElement

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
from .root.block_dictionary import validate_block_dictionary
from .root.block_single import validate_block_single
from .root.block_union import validate_root_block_union
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
    # NB: block_union is intentionally absent. It is a ROOT UI element only (a top-level slot
    # that renders a whole block chosen from a union). A field *inside* a block must never be a
    # block_union, so if one appears the dispatcher raises "not a valid ui_element". The root
    # validator lives in tests/ui_schema/validators/root/block_union.py.
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


# A root-element validator takes (schema, element, ref, config_ref, form) and raises on failure.
RootElementValidator = Callable[[dict, str, str, str, dict], None]

# The single source of truth mapping each root UI element to its validator. Adding a new root
# UI element means adding a module in the root package and an entry here — nothing else.
ROOT_VALIDATOR_BY_UI_ELEMENT: dict[UIElement, RootElementValidator] = {
    UIElement.BLOCK_SINGLE: validate_block_single,
    UIElement.BLOCK_DICTIONARY: validate_block_dictionary,
    UIElement.BLOCK_UNION: validate_root_block_union,
}
