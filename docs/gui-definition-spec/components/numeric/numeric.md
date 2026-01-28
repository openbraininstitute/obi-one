## Float parameter sweep

ui_element: `float_parameter_sweep`

- Should have an `anyOf` property.
- Should accept a `number` and `number array`.
- _The single `number` value must come first_.
- Optional `minimum` and `maximum` and `default` in both cases.
- Optional `units` string.

Reference schema [float_parameter_sweep](reference_schemas/float_parameter_sweep.jsonc)

### Example Pydantic implementation

```py

class Block:

    extracellular_calcium_concentration:  NonNegativeFloat | list[NonNegativeFloat] = Field( # The single value must come first in the union
            ui_element="float_parameter_sweep",
            default=1.1,
            title="Extracellular Calcium Concentration",
            description=(
                "Extracellular calcium concentration",
            ),
            units="mM",
        )

```

### UI design

<img src="designs/float_parameter_sweep.png"  width="300" />

## Integer parameter sweep

ui_element: `int_parameter_sweep`

- Same as `parameter_sweep` but with `int` types in the `anyOf` array.

Reference schema [int_parameter_sweep](reference_schemas/int_parameter_sweep.jsonc)

### Example Pydantic implementation

```py
class Block:
    random_seed: int | list[int] = Field(
            ui_element="int_parameter_sweep",
            default=1,
            title="Random seed"
            description="Random seed for the simulation."
        )

```