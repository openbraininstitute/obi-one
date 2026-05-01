## Reference

ui_element: `reference`

[reference/reference.md](reference/reference.md).

- Should accept as input an `object` with `string` fields `block_name` and `block_dict_name`.
- Second element should be `null`.
- Should have a non-validating `reference_types` array of strings, listing every reference type the field accepts. Each entry is the class name of a `BlockReference` subclass and must match the type of one of the references allowed by the field's union.

_References are hidden from the UI if either the `ui_hidden` property is `True` or none of the entries in `reference_types` is present in its configuration's `default_block_reference_labels` [See](../../gui-definition.md#scanconfigs-additional).

Reference schema [reference](reference_schemas/reference.json)

### Example Pydantic implementation

A field that accepts a single reference type still uses a list with one element:

```py
class Block:
    node_set: NeuronSetReference | None = Field(default=None, # Must be present
                                                title="Neuron Set",
                                                description="Neuron set to simulate.",
                                                json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                                                                    SchemaKey.REFERENCE_TYPES: [NeuronSetReference.__name__]}
                                                )
```

A field that accepts a union of reference types lists each one:

```py
class Recording:
    neuron_set: BiophysicalNeuronSetReference | PointNeuronSetReference | TimestampsReference | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set to record from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [
                BiophysicalNeuronSetReference.__name__,
                PointNeuronSetReference.__name__,
                TimestampsReference.__name__,
            ],
        },
    )
```

A pre-defined module-level list constant can also be passed directly (e.g. `NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES` in `unions_neuron_sets_2.py`).

### UI design

<img src="designs/reference.png"  width="300" />
