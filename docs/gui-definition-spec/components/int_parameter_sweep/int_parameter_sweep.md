## Integer parameter sweep

UIElement: `UIElement.INT_PARAMETER_SWEEP`

- Same as `UIElement.FLOAT_PARAMETER_SWEEP` but with `int` types in the `anyOf` array.

Reference schema [int_parameter_sweep](reference_schemas/int_parameter_sweep.jsonc)

### Example Pydantic implementation

```py
class Block:
    random_seed: int | list[int] = Field(
            default=1,
            title="Random seed"
            description="Random seed for the simulation.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP})
        )

```
