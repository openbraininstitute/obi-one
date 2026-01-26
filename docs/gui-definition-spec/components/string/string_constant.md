## String constant

ui_element: `string_constant`

These represent string variables which should display in the UI but currently cannot be selected.

### Example Pydantic implementation

```py

```

### UI design

String constants appear exactly as [string_selection](string_selection.md) elements in their closed position, except, that the dropdown arrow should not appear.

String constants can also use [string_extra](string_extra.md) properties; notably latex, description, or both together.