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

## Adding ui_elements to the spec

**If a config requires ui elements not specified in the current spec they must be added by defining a `ui_element` string, a reference schema and corresponding validation scripts, and a UI design**

Any ui elements sharing the same `ui_element` string must share the same pydantic implementation (and by extension the same json schema). 

For example the following would be an incorrect use of `ui_element` since the resulting schemas differ in structure, `field_A` is of `integer` type where as `field_B` contains an `anyOf` property.

```py
# ❌ Wrong use of ui_element

class Block:
    field_A: int = Field(ui_element="integer_input", ...)
    field_B: int | None = Field(ui_element="integer_input", ...)
```

```jsonc

// Schemas differ in structure 

"field_A": {
      "title": "Field A",
      "type": "integer",  
      "ui_element": "integer_input"
    },

"field_B": {
      "title": "Field B",
      "anyOf": [ // anyOf
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "ui_element": "integer_input"
    }

```

In such cases either make them consistent or create separate `ui_element`s.

```py
# ✅ Consistent types
class Block:
    field_A: int | None = Field(ui_element="integer_input", ...)
    field_B: int | None = Field(ui_element="integer_input", ...)

```

```py
# ✅ Separate ui_elements
class Block:
    field_A: int = Field(ui_element="integer_input", ...)
    field_B: int | None = Field(ui_element="nullable_integer_input", ...)
```

### Writing validation scripts

For each new `ui_element` a corresponding validation function must be added to [validate_root_element](../scripts/validate_schema.py#L30) in case of new root elements or to [validate_block_elements](../scripts/validate_block.py#L210) in the case of new block elements.

The purpose of validation functions is twofold:
1. Ensure that the schema of the element matches the structure the frontend needs to render the input element.
2. Ensure the element accepts as input the types the frontend is expected to produce.

For example [block dictionaries](#block_dictionary) require that the `oneOf` property is present in the schema, since it renders the elements of that array, therefore the script must check it exists:

```py
def validate_block_dictionary(schema: dict, key: str, config_ref: str) -> None:
    if schema.get("additionalProperties", {}).get("oneOf") is None:
        msg = (
            f"Validation error at {config_ref}: block_dictionary {key} must have 'oneOf'"
            "in additionalProperties"
        )
        raise ValueError(msg)

    ...

```

To check the expected input types are accepted by the `ui_element` one can simply use `validate` from the `jsonschema` library. 
For example the `float_parameter_sweep` must accept a `float` or a `list[float]`, so that's what we check:

```py
def validate_float_param_sweep(param_schema: dict, param: str, ref: str) -> None:
     
    ##... We check input types after checking the schema structure

    try:
        validate(1.0, param_schema)

    except ValidationError:
        msg = (
                f"Validation error at {ref}: float_parameter_sweep param {param} failed "
                "to validate a float"
            )
        raise ValidationError(msg) from None

    try:
        validate([1.0], param_schema)

    except ValidationError:
        msg = (
                f"Validation error at {ref}: float_parameter_sweep param {param} failed "
                "to validate a float array"
            )
        raise ValidationError(msg) from None
```


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

[root_block/root_block.md](root_block/root_block.md)

[block_dictionary/block_dictionary.md](block_dictionary/block_dictionary.md)

## Block elements

Block elements are properties of blocks, they must have a `ui_element` property.
The parents of block elements must be blocks, never scan configs

They should contain a `title` and a `description`.

## String input

ui_element: `string_input`

Represents a simple input field.

The type should be `string`.

Reference schema: [string_input](reference_schemas/string_input.json)

### Example Pydantic implementation

```py
class Block:
    field: str = Field(ui_element="string_input",
                      min_length=1,
                      title="title",
                      description="description")
```

### UI design

<img src="designs/string_input.png" width="300" />

## Model identifier

ui_element: `model_identifier`

- Should accept as input an object including an `id_str` string field.

Reference schema [model_identifier](reference_schemas/model_identifier.jsonc)

### Example Pydantic implementation

```py

class Circuit:
    pass

# Required
class CircuitFromId(OBIBaseModel):
    id_str: str = Field(description="ID of the entity in string format.")


class Block:
    circuit: Circuit | CircuitFromId = Field( # Other elements in the union other than `CircuitFromId` not required.
            ui_element="model_identifier",
            title="Circuit", description="Circuit to simulate."
        )
```

### UI design

<img src="designs/model_identifier.png"  width="300" />





[numeric/numeric.md](numeric/numeric.md)
[reference/reference.md](reference/reference.md)




## Entity property dropdown

ui_element: `entity_property_dropdown`

- Should accept a single `string` as input.
- Should have an `entity_type` non-validating string.
- Should have a `property` non-validating string.

Reference schema [entity_property_dropdown](reference_schemas/entity_property_dropdown.json)

### Example Pydantic implementation

```py
CircuitNode = Annotated[str, Field(min_length=1)] # Required in the schema
NodeSetType = CircuitNode | list[CircuitNode] # list[] not required

class Block:

    node_set: NodeSetType = Field(
        ui_element="entity_property_dropdown",
        entity_type=EntityType.CIRCUIT,
        property=CircuitPropertyType.NODE_SET,
        title="Node Set",
        description="Name of the node set to use.",
        min_length=1,
    )
    
```

### UI design

<img src="designs/entity_property_dropdown.png"  width="300" />

## Legacy elements

## Neuron ids

ui_element: `neuron_ids`

This element's schema is particularly disordered, we have to keep it for legacy reasons (to avoid breaking changes to the schema). But it shouldn't be used in new configs.

Reference schema [neuron_ids](reference_schemas/neuron_ids.json)

Current pydantic implementation (`ui_element` added) for reference:

```py
class Block:
    neuron_ids: NamedTuple | list[NamedTuple] = Field(ui_element="neuron_ids", min_length=1, title="neuron ids", description="description")

```
