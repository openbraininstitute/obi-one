## Distance function input (nullable)

ui_element: `distance_function_input_nullable`

Same editor, validation, and rules as
[distance_function_input](../distance_function_input/distance_function_input.md). The only
difference is the schema shape and, therefore, where the outer component reads `max_length` from.
See the main document for everything about the editor, the validation endpoint, and the enforced
rules.

### Schema structure

This element is for a nullable `str | None` field. Pydantic emits it as an `anyOf` rather than a
plain `string`, so `maxLength` is not at the schema root:

```json
{
  "anyOf": [{ "type": "string", "maxLength": 500 }, { "type": "null" }],
  "default": null,
  "ui_element": "distance_function_input_nullable"
}
```

The string branch must come **first** and carry `max_length=MAX_DISTANCE_FUNCTION_LENGTH`; the
second branch is `null`. The frontend component reads `maxLength` from `anyOf[0]` (a fixed position).

The schema test `validate_distance_function_input_nullable` (in
`tests/ui_schema/validate_block.py`) enforces this shape: it requires the two-branch `anyOf`,
string first with `max_length` on it, null second.

### Example Pydantic implementation

Used by the abstract base distribution block (default `None`):

```py
class DistanceDependentDistribution(Block):
    function: str | None = Field(
        default=None,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description=(
            "Expression using {value} and {distance}; custom expressions may also use "
            "placeholders defined by the corresponding parameter configuration."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT_NULLABLE},
    )
```
