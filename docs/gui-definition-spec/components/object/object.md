## Object

ui_element: `object`

A fixed-shape object that becomes a plain dictionary in Python. Unlike
[block_dictionary](../block_dictionary/block_dictionary.md) (an open, arbitrarily-keyed map of
blocks), an `object` has a **closed, declared** set of properties. The frontend reads the object's
`properties` and renders each one using its own nested block-element `ui_element`.

Rules:
- The type must be `object`.
- `additionalProperties` must be `false`. Undeclared keys are not allowed, because there is no
  schema to validate them against.
- Each declared property must have a `title`, a `description`, and a nested block-element
  `ui_element`. The currently supported nested types are:
  - `boolean_input`
  - `float_input`
  - `string_input`
  - `string_list_input`

### Example Pydantic implementation

```py
class EfelSettings(Block):
    strict_stiminterval: bool = Field(
        default=True,
        title="Strict stim interval",
        description="Enforce strict stimulus-interval checks in eFEL feature extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interp_step: PositiveFloat = Field(
        default=0.025,
        title="Interpolation step",
        description="Interpolation step (ms) used by eFEL when resampling traces.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT},
    )


class OptimizationSettings(Block):
    efel_settings: EfelSettings = Field(
        default_factory=EfelSettings,
        title="eFEL settings",
        description="Common eFEL settings forwarded to optimization evaluations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.OBJECT},
    )
```

### UI design

(To be specified.)
