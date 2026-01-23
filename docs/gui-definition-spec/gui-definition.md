# Specification for JSONSchema GUI definition

## ScanConfigs

ScanConfigs intended for the UI require the `ui_enabled` (boolean) property. Setting this to `true` triggers the validation; only configs complying with the specification can be integrated into the UI. The ScanConfig is considered valid if its schema is valid and the schemas of all its elements (root elements and block elements) are valid.

<!-- All root elements and block elements must be a valid `ui_element`. [See below for details](#valid-ui_elements). -->

<!-- ### Constraints -->

All properties of a scan config must be _root elements_.

Scan configs should contain `group_order` property which must be an array of strings determining the order in which groups of root elements appear in the UI. All values in `group_order` must be present in at least one root element's `group` string.

Optionally, scan configs should contain a `default_block_element_labels` dictionary, specifying the labels for null references used in the config. If a `reference` used in the config isn't in this dictionary it will be hidden from the UI.

[Scan config example schema](scan_config/scan_config.jsonc)

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




## Hidden elements

Setting the property `ui_hidden` to `true` will hide it from the UI. All hidden elements must have a `default`.

### Example

```py
class Block:
    field: str = Field(default="hidden input",  # Default must be present if ui_hidden==True
                        ui_hidden=True,
                        ui_element="string_input",
                        title="title",
                        description="description")
```

## Root elements

_root elements_ are the properties of scan configs they can be either _root blocks_ or _block dictionaries_ .

Root elements must have the following properties:
- `group` string that points to a string in its parent config's `group_order` array.
- `group_order` integer (unique within the group) which determines the in which the root element appears within its specified `group`.
- `title` 
- `description`

Currently supported root elements:

- [root_block](ui_elements/root_block/root_block.md)

- [block_dictionary](ui_elements/block_dictionary/block_dictionary.md)

## Block elements

Block elements are properties of blocks. The parents of block elements must be blocks, never scan configs. Blocks must have the following properties:
- `ui_element`
- `title`
- `description`


Currently supported block elements:

- [string](ui_elements/string/string.md)

- [model_identifier](ui_elements/model_identifier/model_identifier.md)

- [numeric](ui_elements/numeric/numeric.md)

- [reference](ui_elements/reference/reference.md)

- [entity_property_dropdown](ui_elements/entity_property_dropdown/entity_property_dropdown.md)

Legacy block elements:

- [neuron_ids](ui_elements/neuron_ids/neuron_ids.md)


## Contributing

[Adding New UI Elements](contributing/adding_new_ui_elements/adding_new_ui_elements.md)

[Writing Validation Scripts](contributing/writing_validation_scripts/writing_validation_scripts.md)