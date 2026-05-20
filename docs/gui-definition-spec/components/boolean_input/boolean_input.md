## Boolean input

ui_element: `boolean_input`

Represents a boolean input field (checkbox).

The type should be `boolean`.

Reference schema: [boolean_input](reference_schemas/boolean_input.json)

### Example Pydantic implementation

```py
class Block:
    field: bool = Field(
                       default=False,
                       title="title",
                       description="description",
                       json_schema_extra={
                            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
                            SchemaKey.GROUP: "Group 1", # Must be present in its parent's config `group_order` array,
                            SchemaKey.GROUP_ORDER: 0, # Unique within the group.
                        } 
                    )
```

### UI design

<img src="designs/boolean_input.png" width="300" />
