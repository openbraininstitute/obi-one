## Reference

ui_element: `reference`

[reference/reference.md](reference/reference.md).

- Should accept as input an `object` with `string` fields `block_name` and `block_dict_name`.
- Second element should be `null`.
- Should have a string (non-validating) `reference_type`, which is consitent with the type of the reference.

_References are hidden from the UI if either the `ui_hidden` property is `True` or their `reference_type` is missing in its configuration's `default_block_reference_labels` [See](../../gui-definition.md#scanconfigs-additional).

Reference schema [reference](reference_schemas/reference.json)

### Example Pydantic implementation

```py
class Block:
    node_set: NeuronSetReference | None = Field(default=None, #Must be present
                                                title="Neuron Set",
                                                description="Neuron set to simulate.",
                                                json_schema_extra={"ui_element": "reference",
                                                                    "reference_type": "NeuronSetReference"}
                                                )
```

### UI design

<img src="designs/reference.png"  width="300" />