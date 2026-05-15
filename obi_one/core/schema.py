from enum import StrEnum


class SchemaKey(StrEnum):
    ACCEPTED_INPUT_TYPES = "accepted_input_types"
    BLOCK_USABILITY_DICTIONARY = "block_usability_dictionary"
    DEFAULT_BLOCK_REFERENCE_LABELS = "default_block_reference_labels"
    DESCRIPTION_BY_KEY = "description_by_key"
    ENTITY_QUERY = "entity_query"
    FALSE_MESSAGE = "false_message"
    FILTERS = "filters"
    GROUP = "group"
    GROUP_ORDER = "group_order"
    LATEX_BY_KEY = "latex_by_key"
    LATEX_EQUATION = "latex_equation"
    PROPERTY = "property"
    PROPERTY_ENDPOINTS = "property_endpoints"
    PROPERTY_GROUP = "property_group"
    REFERENCE_TYPE = "reference_type"
    SINGULAR_NAME = "singular_name"
    SUPPORTS_VIRTUAL = "supports_virtual"
    TITLE_BY_KEY = "title_by_key"
    UI_ELEMENT = "ui_element"
    UI_ENABLED = "ui_enabled"
    UI_HIDDEN = "ui_hidden"
    UNITS = "units"


class UIElement(StrEnum):
    BLOCK_DICTIONARY = "block_dictionary"
    BLOCK_SINGLE = "block_single"
    BLOCK_UNION = "block_union"
    BOOLEAN_INPUT = "boolean_input"
    ENTITY_PROPERTY_DROPDOWN = "entity_property_dropdown"
    FLOAT_PARAMETER_SWEEP = "float_parameter_sweep"
    INT_PARAMETER_SWEEP = "int_parameter_sweep"
    ION_CHANNEL_VARIABLE_MODIFICATION_BY_NEURON = "ion_channel_variable_modification_by_neuron"
    ION_CHANNEL_VARIABLE_MODIFICATION_BY_SECTION_LIST = (
        "ion_channel_variable_modification_by_section_list"
    )
    MODEL_IDENTIFIER = "model_identifier"
    MODEL_IDENTIFIER_MULTIPLE = "model_identifier_multiple"
    MODEL_SELECTOR_SINGLE = "model_selector_single"
    NEURON_IDS = "neuron_ids"
    REFERENCE = "reference"
    SELECT_RECORDABLE_ION_CHANNEL_VARIABLE = "select_recordable_ion_channel_variable"
    STRING_CONSTANT = "string_constant"
    STRING_CONSTANT_ENHANCED = "string_constant_enhanced"
    STRING_INPUT = "string_input"
    STRING_SELECTION = "string_selection"
    STRING_SELECTION_ENHANCED = "string_selection_enhanced"
    VOLTAGE_DURATION = "voltage_duration"


class AcceptedInputTypes(StrEnum):
    """Contains types that can be used as inputs.

    For now, is only used for models that use a subclass of NamedTuples as input
    to make explicit the accepted types of models.
    Can be extended in the future if needed.
    """

    CELL_MORPHOLOGY_FROM_ID = "CellMorphologyFromID"
    ME_MODEL_FROM_ID = "MEModelFromID"
