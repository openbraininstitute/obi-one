## Adding ui_elements to the spec

**If a config requires ui elements not specified in the current spec they must be added by defining a `UIElement` enum member, a reference schema and corresponding validation scripts, and a UI design**

Any ui elements sharing the same `UIElement` value must share the same pydantic implementation (and by extension the same json schema).

For example the following would be an incorrect use of `UIElement` since the resulting schemas differ in structure, `field_A` accepts `int | list[int]` where as `field_B` accepts `float | list[float]`.

```py
# ❌ Wrong use of UIElement

class Block:
    field_A: int | list[int] = Field(json_schema_extra={
                                            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP, ...
                                        })
    field_B: float | list[float] = Field(json_schema_extra={
                                            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP, ...
                                        })
```

```jsonc

// Schemas differ in structure

"field_A": {
      "title": "Field A",
      "anyOf": [{"type": "integer"}, {"type": "array", "items": {"type": "integer"}}],
      "ui_element": "int_parameter_sweep"
    },

"field_B": {
      "title": "Field B",
      "anyOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}}],
      "ui_element": "int_parameter_sweep"
    }

```

In such cases either make them consistent or create separate `UIElement`s.

```py
# ✅ Consistent types
class Block:
    field_A: int | list[int] = Field(json_schema_extra={
                                        SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP, ...
                                    })
    field_B: int | list[int] = Field(json_schema_extra={
                                        SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP, ...
                                    })

```

```py
# ✅ Separate UIElements
class Block:
    field_A: int | list[int] = Field(json_schema_extra={
                                        SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP, ...
                                    })
    field_B: float | list[float] = Field(json_schema_extra={
                                        SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP, ...
                                    })
```
