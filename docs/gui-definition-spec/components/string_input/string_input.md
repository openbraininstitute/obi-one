## String input

ui_element: `string_input`

Represents a simple input field.

The type should be `string`.

Reference schema: [string_input](reference_schemas/string_input.json)

### Example Pydantic implementation

```py
class Block:
    field: str = Field(min_length=1,
                      title="title",
                      description="description",
                    json_schema_extra={"ui_element": "reference",
                                        "reference_type": "NeuronSetReference"})
```

### UI design

<img src="designs/string_input.png" width="300" />