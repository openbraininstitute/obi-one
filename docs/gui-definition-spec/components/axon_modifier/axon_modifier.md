## Axon modifier

ui_element: `axon_modifier`

A one-off element for the BluePyEModel `axon_modifier` selection. It behaves like
[string_selection_enhanced](../string/string_selection.md#string-selection-enhanced) (a dropdown
with per-option titles and descriptions), with one structural difference: the field is typed as
the `AxonModifier` enum **class** rather than an inline `Literal`.

Because the field type is a named enum class, Pydantic serialises it as a `$ref` to a shared
enum definition instead of inlining `type`/`enum` on the property. The validator resolves that
`$ref` before applying the enhanced-selection checks. This element exists specifically to handle
that case and should not be reused for ordinary string dropdowns — prefer `string_selection` or
`string_selection_enhanced` (inline `Literal`) for those.

The element must specify:
- `title_by_key`: a dict with a human-readable title for each enum value.
- `description_by_key`: a dict with a description for each enum value.

Both dictionaries must have keys that exactly match the enum values.

### Example Pydantic implementation

```py
class MorphologySettings(Block):
    axon_modifier: AxonModifier = Field(
        default=AxonModifier.replace_axon_with_taper,
        title="Axon replacement",
        description="BluePyEModel axon strategy.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.AXON_MODIFIER,
            SchemaKey.TITLE_BY_KEY: AXON_MODIFIER_TITLES,
            SchemaKey.DESCRIPTION_BY_KEY: {
                modifier.value: description
                for modifier, description in AXON_MODIFIER_DESCRIPTIONS.items()
            },
        },
    )
```

### UI design

(To be specified.)
