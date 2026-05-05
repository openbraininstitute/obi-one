## String constant

UIElement: `UIElement.STRING_CONSTANT`

These represent string variables which should display in the UI but currently cannot be selected.

### Example Pydantic implementation

```py
class Block:
    field: Literal["A"] = Field(
        title="Constant",
        description="Constant description.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_CONSTANT
        }
    )
```

### UI design

String constants appear exactly as [string_selection](../string_selection/string_selection.md) elements in their closed position, except, that the dropdown arrow should not appear.


## String constant enhanced

UIElement: `UIElement.STRING_CONSTANT_ENHANCED`

Reference schema: [string_constant_enhanced](reference_schemas/string_constant_enhanced.json)

### Example Pydantic implementation

String constants can also use the enhaced style described for [string_selection_enhanced](../string_selection/string_selection.md#string-selection-enhanced) with `SchemaKey.DESCRIPTION_BY_KEY` and/or `SchemaKey.LATEX_BY_KEY` options.

### UI Design

These use the same visual appearance as the string_selection_enhanced UI elements in the closed position, except without the dropdown arrow.