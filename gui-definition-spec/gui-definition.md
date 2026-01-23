# Specification for JSONSchema GUI definition

## Scan configs

### ui_enabled

Scan configs intended for the UI require the `ui_enabled` (boolean) property. Setting this to `true` triggers the validation; only configs complying with the specification can be integrated into the UI.

The config is considered valid if its schema is valid and the schemas of all its root elements and block elements are valid.
All root elements and block elements must have a valid `ui_element`. [See below for details](#valid-ui_elements).

### Constraints

All properties of a scan config must be _root elements_. (See below).

They should contain `group_order` property which must be an array of strings determining the order of groups of root elements. All values in `group_order` must be present in at least one root element's `group` string.

Optionally, they should contain a `default_block_element_labels` dictionary, specifying the labels for null references used in the config. If a `reference` used in the config isn't in this dictionary it will be hidden from the UI.

Reference schema: [scan_config](reference_schemas/scan_config.jsonc)

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


[Adding New UI Elements](adding_new_ui_elements)

[Writing Validation Scripts](writing_validation_scripts)

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

They should contain a `group` string that points to a string in its parent config's `group_order` array.

They should contain a `group_order` integer (unique within the group).

They should contain a `title` and a `description`.

[root_block](root_block/root_block.md)

[block_dictionary](block_dictionary/block_dictionary.md)

## Block elements

Block elements are properties of blocks, they must have a `ui_element` property.
The parents of block elements must be blocks, never scan configs

They should contain a `title` and a `description`.

[string](string/string.md)

[model_identifier](model_identifier/model_identifier.md)

[numeric](numeric/numeric.md)

[reference](reference/reference.md)

[entity_property_dropdown](entity_property_dropdown/entity_property_dropdown.md)

## Legacy elements

[neuron_ids](neuron_ids/neuron_ids.md)
