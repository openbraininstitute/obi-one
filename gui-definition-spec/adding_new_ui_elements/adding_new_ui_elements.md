## Adding ui_elements to the spec

**If a config requires ui elements not specified in the current spec they must be added by defining a `ui_element` string, a reference schema and corresponding validation scripts, and a UI design**

Any ui elements sharing the same `ui_element` string must share the same pydantic implementation (and by extension the same json schema). 

For example the following would be an incorrect use of `ui_element` since the resulting schemas differ in structure, `field_A` is of `integer` type where as `field_B` contains an `anyOf` property.

```py
# ❌ Wrong use of ui_element

class Block:
    field_A: int = Field(ui_element="integer_input", ...)
    field_B: int | None = Field(ui_element="integer_input", ...)
```

```jsonc

// Schemas differ in structure 

"field_A": {
      "title": "Field A",
      "type": "integer",  
      "ui_element": "integer_input"
    },

"field_B": {
      "title": "Field B",
      "anyOf": [ // anyOf
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "ui_element": "integer_input"
    }

```

In such cases either make them consistent or create separate `ui_element`s.

```py
# ✅ Consistent types
class Block:
    field_A: int | None = Field(ui_element="integer_input", ...)
    field_B: int | None = Field(ui_element="integer_input", ...)

```

```py
# ✅ Separate ui_elements
class Block:
    field_A: int = Field(ui_element="integer_input", ...)
    field_B: int | None = Field(ui_element="nullable_integer_input", ...)
```