## String constant

ui_element: `string_constant`

These represent string variables which should display in the UI but currently cannot be selected.

### Example Pydantic implementation

```py
class Block:
    field: Literal["A"] = Field(
        ui_element="string_constant",
        title="Constant",
        description="Constant description.",
    )
```

### UI design

String constants appear exactly as [string_selection](string_selection.md) elements in their closed position, except, that the dropdown arrow should not appear.


## String constant enhanced

ui_element: `string_constant_enhanced`

Reference schema: [string_constant_enhanced](reference_schemas/string_constant_enhanced.json)

### Example Pydantic implementation

String constants can also use the enhaced style described for [string_selection_enhanced](string_selection.md#string-selection-enhanced) with description_by_key and/or latex_by_key options.

### UI Design

These use the same visual appearance as the string_selection_enhanced UI elements in the closed position, except without the dropdown arrow.