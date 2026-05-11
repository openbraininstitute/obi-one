## Integer tuple parameter sweep

UIElement: `UIElement.INT_TUPLE_PARAMETER_SWEEP`

- Represents grouped integer selections.
- A single grouped selection is encoded as an array of integers.
- A parameter scan over grouped selections is encoded as an array of integer arrays.

Reference schema [int_tuple_parameter_sweep](reference_schemas/int_tuple_parameter_sweep.jsonc)

### Example Pydantic implementation

```py
class Block:
    section_types: tuple[int, ...] | list[tuple[int, ...]] | None = Field(
        default=(3, 4),
        title="Section Types",
        description=(
            "Valid neurite section types to generate locations on."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_TUPLE_PARAMETER_SWEEP
        },
    )