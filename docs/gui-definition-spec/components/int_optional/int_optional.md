## Int optional

UIElement: `UIElement.INT_OPTIONAL`

A nullable integer input: an `integer` or `null`, where `null` means "not set". It is **not** swept.

Reference schema [int_optional](reference_schemas/int_optional.jsonc)

### Example Pydantic implementation

```py
class Block:
    seed: int | None = Field(
        default=None,
        title="Random seed",
        description="Seed of the sorter's random steps. Unset draws one.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_OPTIONAL},
    )
```

### UI design

_UI design to be added._
