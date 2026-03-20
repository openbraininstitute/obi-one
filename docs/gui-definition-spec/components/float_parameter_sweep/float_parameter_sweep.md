## Float parameter sweep

UIElement: `UIElement.FLOAT_PARAMETER_SWEEP`

- Should have an `anyOf` property.
- Should accept a `number` and `number array`.
- _The single `number` value must come first_.
- Optional `minimum` and `maximum` and `default` in both cases.
- Optional `SchemaKey.UNITS` string.

Reference schema [float_parameter_sweep](reference_schemas/float_parameter_sweep.jsonc)

### Example Pydantic implementation

```py

class Block:

    extracellular_calcium_concentration:  NonNegativeFloat | list[NonNegativeFloat] = Field( # The single value must come first in the union
            default=1.1,
            title="Extracellular Calcium Concentration",
            description=(
                "Extracellular calcium concentration",
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT=UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS="mM"
            }
        )

```

### UI design

<img src="designs/float_parameter_sweep.png"  width="300" />
