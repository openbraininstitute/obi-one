# Specification for JSONSchema GUI definition

## ScanConfigs

ScanConfigs intended for the UI require the `ui_enabled` (boolean) property. Setting this to `true` triggers the validation; only configs complying with the specification can be integrated into the UI. The ScanConfig is considered valid if its schema is valid and the schemas of all its elements are valid.

Different elements of the scan config are of different type specified by the `ui_element`. 

ScanConfigs are composed of `Root elements`. There are currently two supported root elements:
        - [root_block](components/root_block/root_block.md)
        - [block_dictionary](components/block_dictionary/block_dictionary.md)

    - Root elements must have the following properties:
        - `group` string that points to a string in its parent config's `group_order` array.
        - `group_order` integer (unique within the group) which determines the in which the root element appears within its specified `group`.
        - `title` 
        - `description`

- `group_order` property which must be an array of strings determining the order in which groups of root elements appear in the UI. All values in `group_order` must be present in at least one root element's `group` string.

- `default_block_element_labels` (optional), specifying the labels for null references used in the config. If a `reference` used in the config isn't in this dictionary it will be hidden from the UI.

See the [Example scan config schema](components/scan_config/scan_config.jsonc)



<!-- All root elements and block elements must be a valid `ui_element`. [See below for details](#valid-ui_elements). -->

<!-- ### Constraints -->

<!-- All properties of a scan config must be _root elements_. -->

<!-- Scan configs should contain `group_order` property which must be an array of strings determining the order in which groups of root elements appear in the UI. All values in `group_order` must be present in at least one root element's `group` string.

Optionally, scan configs should contain a `default_block_element_labels` dictionary, specifying the labels for null references used in the config. If a `reference` used in the config isn't in this dictionary it will be hidden from the UI. -->


## ui_element

All _root elements_ and _block elements_ must include a `ui_element` string that maps the property to a specific UI component. Each `ui_element` identifier corresponds to a strict reference schema. Consequently, if two elements require different schema structures, they must use unique `ui_element` identifiers, even if they are functionally similar.

All ui_elements must contain a `title` and a `description`.

### Valid `ui_element`s

Root elements:

- `root_block`
- `block_dictionary`

Block elements:

- `string_input`
- `model_identifier`
- `float_parameter_sweep`
- `int_parameter_sweep`
- `reference`
- `entity_property_dropdown`


## Root elements

_root elements_ are the properties of scan configs they can be either _root blocks_ or _block dictionaries_ .

Root elements must have the following properties:
- `group` string that points to a string in its parent config's `group_order` array.
- `group_order` integer (unique within the group) which determines the in which the root element appears within its specified `group`.
- `title` 
- `description`

Currently supported root elements:

- [root_block](components/root_block/root_block.md)

- [block_dictionary](components/block_dictionary/block_dictionary.md)

## Block elements

Block elements are properties of blocks. The parents of block elements must be blocks, never scan configs. Blocks must have the following properties:
- `ui_element`
- `title`
- `description`

Block elements can also optionally specifify:
- `unit`


Currently supported block element types:

- [string](components/string/string.md)

- [model_identifier](components/model_identifier/model_identifier.md)

- [numeric](components/numeric/numeric.md)

- [reference](components/reference/reference.md)

- [entity_property_dropdown](components/entity_property_dropdown/entity_property_dropdown.md)

Legacy block elements:

- [neuron_ids](components/neuron_ids/neuron_ids.md)

## Hidden elements

Setting `ui_hidden = true` can be used to [hide](components/ui_hidden/ui_hidden.md) any UI element.

<!-- ['ui_hidden'](components/hidden_element/hidden_element.md) = true can be used to hide any UI element.

- ['ui_hidden'](components/hidden_element/hidden_element.md) = true' -->

## Contributing

[Adding New UI Elements](contributing/adding_new_ui_elements/adding_new_ui_elements.md)

[Writing Validation Scripts](contributing/writing_validation_scripts/writing_validation_scripts.md)