## Float optional

UIElement: `UIElement.FLOAT_OPTIONAL`

A nullable float input: a `number` or `null`, where `null` (an unset value) means
"not set / inherit". Unlike [float_parameter_sweep](../float_parameter_sweep/float_parameter_sweep.md)
it is **not** swept — the alternative to a single `number` is `null`, not an array.

- Should have an `anyOf` property.
- Should accept a `number` and `null`.
- _The single `number` value must come first, `null` second._
- Optional `minimum` / `maximum` on the `number`.
- Optional `SchemaKey.UNITS` string.

It backs the per-protocol and per-feature eFEL detection overrides in the e-feature
extraction cascade (`null` = inherit from the level above: feature > protocol > global).

Reference schema [float_optional](reference_schemas/float_optional.jsonc)

### Example Pydantic implementation

```py

class Block:

    spike_detection_threshold: float | None = Field(  # The single value must come first, then None
            default=None,
            title="Spike detection threshold",
            description=(
                "eFEL Threshold: voltage above which a spike is detected (mV)."
                " Leave unset to inherit from the level above."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
                SchemaKey.UNITS: Units.MILLIVOLTS,
            },
        )

```

### UI design

_UI design to be added._
