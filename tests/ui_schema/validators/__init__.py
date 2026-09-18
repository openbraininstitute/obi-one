"""Locked, per-element validators for block UI elements.

Every block `ui_element` has exactly one validator module in this package. The
`VALIDATOR_BY_UI_ELEMENT` registry (in `registry.py`) maps each `UIElement` to its
validator; the dispatcher in `tests/ui_schema/validate_block.py` looks the validator up
there.

**This package is locked.** Configs must be changed to match the spec these validators
enforce — the validators must not be weakened to make a non-conforming config pass. CI
rejects any PR that touches files under this folder unless the PR carries the
`change-validators` label (see `.github/workflows/run-tests.yml`).

To add a new block UI element:

1. Add the member to `obi_one.core.schema.UIElement`.
2. Create `<new_element>.py` here with a `validate_<new_element>(schema, param, ref)` function.
3. Register it in `VALIDATOR_BY_UI_ELEMENT` in `registry.py`.
4. Because steps 2-3 touch this locked folder, apply the `change-validators` label so a
   reviewer signs off.
"""

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
from .registry import VALIDATOR_BY_UI_ELEMENT, BlockElementValidator
from .select_efeatures_by_protocol import validate_select_efeatures_by_protocol
from .select_recordable_ion_channel_variable import (
    validate_select_recordable_ion_channel_variable,
)
from .shared import (
    determine_minimum_valid_numeric_value,
    openapi_schema,
    resolve_ref,
    resolve_union_reference_types,
    validate_dictionary_by_enum_key,
    validate_enhanced_string_fields,
    validate_enum_value,
    validate_list_strings,
    validate_numeric_single_and_list_types,
    validate_string,
    validate_string_param,
)
from .string_constant import validate_string_constant
from .string_constant_enhanced import validate_string_constant_enhanced
from .string_input import validate_string_input
from .string_selection import validate_string_selection
from .string_selection_enhanced import validate_string_selection_enhanced
from .voltage_duration import validate_voltage_duration

__all__ = [
    "VALIDATOR_BY_UI_ELEMENT",
    "BlockElementValidator",
    "determine_minimum_valid_numeric_value",
    "openapi_schema",
    "resolve_ref",
    "resolve_union_reference_types",
    "validate_block_union",
    "validate_boolean_input",
    "validate_dictionary_by_enum_key",
    "validate_enhanced_string_fields",
    "validate_entity_property_dropdown",
    "validate_enum_value",
    "validate_float_optional",
    "validate_float_param_sweep",
    "validate_int_param_sweep",
    "validate_ion_channel_variable_modification_by_neuron",
    "validate_ion_channel_variable_modification_by_section_list",
    "validate_list_strings",
    "validate_model_identifier",
    "validate_model_identifier_multiple",
    "validate_model_selector_single",
    "validate_morphology_location_selection",
    "validate_morphology_section_type_selection",
    "validate_neuron_ids",
    "validate_neuron_property_filter",
    "validate_neuron_set_combination",
    "validate_numeric_single_and_list_types",
    "validate_reference",
    "validate_select_efeatures_by_protocol",
    "validate_select_recordable_ion_channel_variable",
    "validate_string",
    "validate_string_constant",
    "validate_string_constant_enhanced",
    "validate_string_input",
    "validate_string_param",
    "validate_string_selection",
    "validate_string_selection_enhanced",
    "validate_voltage_duration",
]
