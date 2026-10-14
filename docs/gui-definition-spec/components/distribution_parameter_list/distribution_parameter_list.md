## Distribution parameter list

ui_element: `distribution_parameter_list`

The list of extra parameters of a custom distance-dependent distribution. Each row is one `{placeholder}` used in the sibling `function` (anything other than `{value}`, `{distance}`, `{step_begin}` and `{step_end}`), together with the value the optimisation uses for it: a fixed value or lower/upper bounds.

Only `CustomDistanceDependentDistribution` has this field. Standard distributions (`uniform`, `exp`, `step`, `sigmoid_*`, ...) have fixed formulas with no extra placeholders, so they show no parameters.

### Behavior

- The function is the source of truth. The editor reads the `{placeholders}` of the sibling `function` field and shows one row per parameter, with the name filled in from the function.
- The user only enters each row's value. The frontend (or AI chat) asks for a value for every row whose value is still empty; the backend does not send prompts.
- When a placeholder is removed from the function, its row goes away; when one is added, a new row appears.
- `value` uses the same fixed/bounds editor as other optimisation values (`mode` is `fixed` or `bounds`; `bounds` must be strictly increasing).

### Schema shape

```json
{
  "type": "array",
  "items": { "$ref": "#/components/schemas/DistributionParameter" },
  "default": [],
  "ui_element": "distribution_parameter_list"
}
```

`DistributionParameter` requires `name` (string matching `^[A-Za-z_]\w*$`) and `value` (`OptimizationValue`).

The schema test `validate_distribution_parameter_list` (in `tests/ui_schema/validators/distribution_parameter_list.py`) enforces this shape: an array defaulting to `[]`, a sibling `function` field in the same block that uses `ui_element: distance_function_input`, items that require `name` and `value`, an identifier `pattern` on `name`, and an `OptimizationValue` with `mode` in `["fixed", "bounds"]`.

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
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTRIBUTION_PARAMETER_LIST},
    )
```

Example value:

```json
[
  { "name": "constant", "value": { "mode": "bounds", "bounds": [-0.1, 0.0] } }
]
```
