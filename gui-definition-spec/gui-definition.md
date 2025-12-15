# Specification for JSONSchema GUI definition

## Forms

### ui_enabled

Forms intended for the UI require the `ui_enabled` (boolean) property. Setting this to `true` triggers the validation; only forms complying with the specification can be integrated into the UI.

### group_order

The `group_order` property must be an array of strings determining the order of groups.
All values must reference valid entries in `root_element`s.

### Important considerations

All properties of a form must be _root elements_. (See below)
The `group` integer of every root element in the form must be unique.

Reference schema: [form_schema.json](form_schema.json)

## ui_element

All _root elements_ and _block elements_ must include a `ui_element` string that maps the form data to a specific UI component. Each `ui_element` identifier corresponds to a strict reference schema. Consequently, if two components require different schema structures, they must use unique `ui_element` identifiers, even if they are functionally similar.

_More details below_

## Root elements

_root elements_ are the properties of forms they can be either _root blocks_ or _block dictionaries_ .

## root_block

ui_element: `root_block`

Root blocks are blocks defined at the root level of a form.
They should contain `properties` in it's schema which are _block_elements_.
They should contain a `group` string that points to a string in it's parent form's `group_order` array.
Thay should contain a `group_order` integer (unique within the form).



Each key in the root schema definition has a form subschema.

_Root forms_, render a form. For example `initialize`.

_Block forms_, render selection cards with _block types_ to create a new _block_. E.g `neuron_sets`

# Groups and parent blocks

```json
group_order: [ "Setup", "Stimuli & Recordings", "Circuit Components", ]
```

The schema for each of the parent blocks should contain both the group to which it belongs and the order within the group:

```json
initialize: {
    "group": "Setup",
    "group_order": 1
}
```

### Root forms

Root forms should this spec.

    type: 'object' 🔴 Always literally 'object'.
    title: string
    description: string
    group: string
    group_order: number
    additionalProperties: false 🔴 Always false
    properties: object # A JSONschema object defining the fields of the form, see below for spec.
    required: string array: # Required properties

### Block forms

Block forms should follow this spec.

    type: 'object' 🔴 Always object
    title: string
    description: string
    group: string
    group_order: number

    additionalProperties: object, 🟡 Block forms should always contain an additionalProperties object with a single field, "oneOf". See below for spec.
    reference_type: string
    singular_name: string

🟡 Block forms should not contain "properties" or "required" fields.

#### additionalProperties spec for block forms

The additionalProperties field is used to define the spec that renderes the block type selection. (e.g the list of "ID Neuron Set", "All Neurons", etc.)

It should be an object following this spec:

    oneOf: An array of objects defining each of the different block types, see below.

Block forms' "additionalProperties" object should only contain "oneOf" and no other fields.

##### oneOf spec for block forms

Each block type in the oneOf array should follow this spec:

    type: "object"
    title: string
    description: string
    properties: Object with the fields of the form, see below for spec.
    required: Required fields array
    additionalProperties: false
    ​​​​​​​​​​

## Form fields (parameters)

Form fields (either for block forms or root forms) should follow this spec.
