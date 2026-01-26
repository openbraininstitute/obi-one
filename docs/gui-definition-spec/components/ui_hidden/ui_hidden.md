## Hidden elements

Any element can hidden in the UI by specifying the `ui_hidden = true`. All hidden elements must have a `default`.

### Example

```py
class Block:
    field: str = Field(default="hidden input",  # Default must be present if ui_hidden==True
                        ui_hidden=True,
                        ui_element="string_input",
                        title="title",
                        description="description")
```
