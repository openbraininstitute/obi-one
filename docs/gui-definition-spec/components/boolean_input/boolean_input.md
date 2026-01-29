## Boolean input

ui_element: `boolean_input`

Represents a boolean input field (checkbox).

The type should be `boolean`.

Reference schema: [boolean_input](reference_schemas/boolean_input.json)

### Example Pydantic implementation

```py
class Block:
    field: bool = Field(ui_element="boolean_input",
                       default=False,
                       title="title",
                       description="description")
```

### UI design

<img src="designs/boolean_input.png" width="300" />
