from enum import StrEnum


class UIElement(StrEnum):
    BLOCK_DICTIONARY = "block_dictionary"
    BLOCK_SINGLE = "block_single"
    BLOCK_UNION = "block_union"
    BOOLEAN_INPUT = "boolean_input"
    ENTITY_PROPERTY_DROPDOWN = "entity_property_dropdown"
    FLOAT_PARAMETER_SWEEP = "float_parameter_sweep"
    INT_PARAMETER_SWEEP = "int_parameter_sweep"
    ION_CHANNEL_VARIABLE_MODIFICATION_BY_NEURON = "ion_channel_variable_modification_by_neuron"
    ION_CHANNEL_VARIABLE_MODIFICATION_BY_SECTION_LIST = "ion_channel_variable_modification_by_section_list"
    MODEL_IDENTIFIER = "model_identifier"
    MODEL_SELECTOR_SINGLE = "model_selector_single"
    NEURON_IDS = "neuron_ids"
    REFERENCE = "reference"
    SELECT_RECORDABLE_ION_CHANNEL_VARIABLE = "select_recordable_ion_channel_variable"
    STRING_CONSTANT = "string_constant"
    STRING_CONSTANT_ENHANCED = "string_constant_enhanced"
    STRING_INPUT = "string_input"
    STRING_SELECTION = "string_selection"
    STRING_SELECTION_ENHANCED = "string_selection_enhanced"
