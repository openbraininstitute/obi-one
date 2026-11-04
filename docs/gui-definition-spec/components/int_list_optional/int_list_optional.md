## Int list optional

UIElement: `UIElement.INT_LIST_OPTIONAL`

A nullable list of integers. The annotation is a tuple, because a `list` in a block is a scan dimension.

Reference schema [int_list_optional](reference_schemas/int_list_optional.jsonc)

### Example Pydantic implementation

```py
class Block:
    bad_channels: tuple[int, ...] | None = Field(
        default=None,
        title="Bad channels",
        description="Channel indices left out of sorting.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_LIST_OPTIONAL},
    )
```

### UI design

_UI design to be added._
