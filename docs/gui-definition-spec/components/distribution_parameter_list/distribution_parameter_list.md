## Distribution parameter list

ui_element: `distribution_parameter_list`

The list of extra parameters of a custom distance-dependent distribution. Each row is one `{placeholder}` used in the sibling `function` (anything other than `{value}`, `{distance}`, `{step_begin}` and `{step_end}`), together with the value the optimisation uses for it: a fixed value or lower/upper bounds.

Only `CustomDistanceDependentDistribution` has this field. Standard distributions (`uniform`, `exp`, `step`, `sigmoid_*`, ...) have fixed formulas with no extra placeholders, so they show no parameters.

### Behavior

- The field names its source with `parameters_from` (always `"function"`). The editor reads the placeholders from that sibling and lists one row per placeholder.
- When a placeholder has no row, the editor prompts the user to fill it: the row is shown with the name prefilled and the value empty. The prompt text comes from `prompts` in the response of `POST /declared/distance-function/validate` (see [distance_function_input](../distance_function_input/distance_function_input.md#validating-from-the-editor)), so the frontend and the AI chat ask for the same thing.
- Rows whose name is no longer in the function are flagged (`unknown_parameters`) and can be removed.
- `value` uses the same fixed/bounds editor as other optimisation values (`mode` is `fixed` or `bounds`; `bounds` must be strictly increasing).

### Schema shape

```json
{
  "type": "array",
  "items": { "$ref": "#/components/schemas/DistributionParameter" },
  "default": [],
  "ui_element": "distribution_parameter_list",
  "parameters_from": "function"
}
```

`DistributionParameter` requires `name` (string matching `^[A-Za-z_]\w*$`) and `value` (`OptimizationValue`).

The schema test `validate_distribution_parameter_list` (in `tests/ui_schema/validators/distribution_parameter_list.py`) enforces this shape: an array defaulting to `[]`, a `parameters_from` naming a string sibling, items that require `name` and `value`, an identifier `pattern` on `name`, and an `OptimizationValue` with `mode` in `["fixed", "bounds"]`.

### Rules enforced by the backend

- Every extra placeholder in `function` has exactly one row, and every row's name appears in `function`.
- Names are unique and not reserved (`value`, `distance`, `step_begin`, `step_end`).
- Each row's `value` is a valid fixed value or a strictly increasing bounds pair.

### Example Pydantic implementation

```python
class CustomDistanceDependentDistribution(DistanceDependentDistribution):
    parameters: tuple[DistributionParameter, ...] = Field(
        default=(),
        title="Distribution parameters",
        description="One entry per extra {placeholder} used in the function.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.DISTRIBUTION_PARAMETER_LIST,
            SchemaKey.PARAMETERS_FROM: "function",
        },
    )
```

Example value:

```json
[
  { "name": "constant", "value": { "mode": "bounds", "bounds": [-0.1, 0.0] } }
]
```
