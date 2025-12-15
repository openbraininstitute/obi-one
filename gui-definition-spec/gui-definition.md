# Specification for JSONSchema GUI definition

## Forms

### ui_enabled

Forms intended for the UI require the `ui_enabled` (boolean) property. Setting this to `true` triggers the validation; only forms complying with the specification can be integrated into the UI.

### group_order

The `group_order` property must be an array of strings determining the order of groups. All values must be present in at least one properties'
`group`.

### Constraints

All properties of a form must be _root elements_. (See below).

Reference schema: [form_schema.json](form_schema.json)

## ui_element

All _root elements_ and _block elements_ must include a `ui_element` string that maps the form data to a specific UI component. Each `ui_element` identifier corresponds to a strict reference schema. Consequently, if two components require different schema structures, they must use unique `ui_element` identifiers, even if they are functionally similar. _More details below_

## Hidden elements
Setting an elements `ui_element` property to `null` will hide id from the UI. __They must not be required__  (i.e have a `default`).


## Root elements

_root elements_ are the properties of forms they can be either _root blocks_ or _block dictionaries_ .

They should contain a `group` string that points to a string in its parent form's `group_order` array.

They should contain a `group_order` integer (unique within the form).

They should contain a `title` and a `description`.

## root_block

ui_element: `root_block`

Root blocks are blocks defined at the root level of a form.

- They should contain `properties` in its schema which are _block_elements_.
- They should contain a `group` string that points to a string in its parent form's `group_order` array.
- They should contain a `group_order` integer (unique within the form).

Reference schema: [root_block_schema.json](root_block_schema.json)

## block_dictionary

ui_element: `block_dictionary`

- They should contain no `properties`
- They should contain `additionalProperties` with a single `oneOf` array with block schemas.
- They should contain a `singular_name`.
- They should contain a `reference_type`.

Reference schema: [block_dictionary.json](block_dictionary.json)

### Example Pydantic implementation

```py
# Inside its form's class.

neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        ui_element="block_dictionary",
        default_factory=dict,
        reference_type=NeuronSetReference.__name__,
        description="Neuron sets for the simulation.",
        singular_name="Neuron Set",
        group=BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
        group_order=0,
    )

```

### UI design

<img src="block_dictionary.png" alt="description" width="300" />

## Block elements

Block elements are properties of blocks, they (as _root elements_) must have a `ui_element` property.
The parents of block elements must be blocks, never forms.
