# Block ordered

ui_element: `block_ordered`

A [Root UI element](../../gui-definition.md#types-of-ui-element), alongside `block_single`,
`block_union`, and `block_dictionary`.

A `block_ordered` is a block whose `properties` are themselves blocks, rendered in a defined
order. Each contained block declares an integer `order`, and the `order` values must be **unique**
within the block.

## Rules

- Must have `properties`.
- Each property (other than the discriminator `type`) is itself a block and must declare an
  integer `order`.
- The `order` values must be unique across the block's properties.

## Example Pydantic implementation

```py
class MyOrderedBlock(Block):
    first: FirstBlock = Field(
        title="First",
        description="...",
        json_schema_extra={SchemaKey.ORDER: 0},
    )
    second: SecondBlock = Field(
        title="Second",
        description="...",
        json_schema_extra={SchemaKey.ORDER: 1},
    )


class MyScanConfig(ScanConfig):
    my_ordered_block: MyOrderedBlock = Field(
        title="My ordered block",
        description="...",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_ORDERED,
            SchemaKey.GROUP: "Inputs",
            SchemaKey.GROUP_ORDER: 0,
        },
    )
```
