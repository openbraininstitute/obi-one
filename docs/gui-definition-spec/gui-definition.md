# Specification for JSONSchema GUI definition

## ScanConfigs

ScanConfigs intended for the UI require the `ui_enabled` (boolean) property. Setting this to `true` triggers the validation in continuous integration; only configs complying with the specification can be integrated into the UI. The ScanConfig is considered valid if its schema is valid and the schemas of all its elements are valid.

The schema can be tested locally with the command:
`make test-schema`



## UI Elements
Scan configs are composed of multiple UI elements, each corresponding to a variable in the Python definition of the ScanConfig. For example, there is a UI element for specifying a user-defined string:
```py
file_name: str = Field(ui_element="string_input",
                    min_length=1,
                    title="title",
                    description="description")
```

The `ui_element` specified in the Field definition identifies the UI element which should be displayed for user to enter this parameter. Each `ui_element` identifier corresponds to a strict reference schema. Schema validation checks that the definition of the parameter fits with what is expected and required for a `string_input`. Consequently, if two elements require different schema structures, they must use unique `ui_element` identifiers, even if they are functionally similar.

All ui_elements must contain a `title` and a `description`.


## Types of UI element
There are two major types of such UI elements:

1. `Root UI elements` appear in the left hand column of the configuration interface. 
    
    - There are currently three supported types:

        - [block_single](components/block_single/block_single.md)

        - [block_union](components/block_union/block_union.md)

        - [block_dictionary](components/block_dictionary/block_dictionary.md)
        

    - Root elements must have the following properties:
        - `title`
        - `description`
        - `group` string that points to a string in its parent config's `group_order` array.
        - `group_order` integer (unique within the group) which determines the order in which the root element appears within its specified `group`.

    - These properties are added to the root element in the Field definition of the parameter, with the `ui_element` string specifying the type, e.g.:
        ```py
        info: Info = Field(
            ui_element="block_single",
            title="Title",
            description="Description",
            group="Group 1", # Must be present in its parent's config `group_order` array,
            group_order=0, # Unique within the group.
        )
        ```
        
2. `Block UI elements` are properties of blocks. The parents of block elements must be blocks, never scan configs.

    - Currently supported block element types:

        - [string_input](components/string/string_input.md)

        - [string_selection](components/string/string_selection.md) and [string_selection_enhanced](components/string/string_selection.md#string-selection-enhanced)

        - [string_constant](components/string/string_constant.md) and [string_constant_enhanced](components/string/string_constant.md#string-constant-enhanced)

        - [boolean_input](components/boolean_input/boolean_input.md)

        - [model_identifier](components/model_identifier/model_identifier.md)

        - [numeric](components/numeric/numeric.md)

        - [reference](components/reference/reference.md)

        - [entity_property_dropdown](components/entity_property_dropdown/entity_property_dropdown.md)

    - Legacy block elements:

        - [neuron_ids](components/neuron_ids/neuron_ids.md)

    - Blocks elements must have the following properties:
        - `ui_element`
        - `title`
        - `description`

    - Block elements can also optionally specifify:
        - `unit`

    - As for root UI elements these properties are specified in the Field definition of the variable, along with the string `ui_element` specifying the type:
        ```py
        field: str = Field(ui_element="string_input",
                            min_length=1,
                            title="title",
                            description="description")
        ```

    
## ScanConfigs (additional)

Scan configs should additionally have the following property:

- `group_order` property which must be an array of strings determining the order in which groups of root elements appear in the UI. All values in `group_order` must be present in at least one root element's `group` string.

And the following optional property:

- `default_block_element_labels` specifying the labels for null references used in the config. If a `reference` used in the config isn't in this dictionary it will be hidden from the UI.

See the [Example scan config schema](components/scan_config/scan_config.jsonc)

## Hidden elements

Setting `ui_hidden = true` can be used to [hide](components/ui_hidden/ui_hidden.md) any UI element.

## Contributing

[Adding New UI Elements](contributing/adding_new_ui_elements/adding_new_ui_elements.md)

[Writing Validation Scripts](contributing/writing_validation_scripts/writing_validation_scripts.md)