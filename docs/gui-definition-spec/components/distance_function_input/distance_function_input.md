## Distance function input

ui_element: `distance_function_input`

A single-line editor for a distance-dependent distribution `function`: a math expression that
BluePyEModel evaluates per morphology segment (e.g. `math.exp((-{distance})/50.)*{value}`). It
behaves like [string_input](../string/string_input.md) (the stored type is `string`), but the UI
renders a code editor that validates the expression live and shows errors inline.

This element is for a non-nullable `str` field: `maxLength` sits at the schema root, and the outer
component reads it from there. For a nullable `str | None` field, use
[distance_function_input_nullable](../distance_function_input_nullable/distance_function_input_nullable.md),
which carries the same editor but a different schema shape.

### Why this is a distinct element

The function string is user-controlled and reaches Python `eval()` at runtime
(`bluepyemodel.model.model.define_distributions`), so it is both a code-injection surface and an
unbounded-computation (DoS) surface. obi-one enforces a safe, bounded whitelist server-side (see
`validate_safe_distance_function`) and exposes the same check through a validation endpoint so the
editor can give instant feedback. The backend remains the security boundary; the client check is a
convenience layer only.

### Validating from the editor

The editor should not reimplement the whitelist. It calls the backend validation endpoint and
renders the structured result:

`POST /declared/distance-function/validate`

Request:

```json
{ "function": "math.exp((-{distance})/50.)*{value}", "parameters": ["constant"] }
```

Response:

```json
{ "valid": false, "error": "Distance function contains ...", "from": 4, "to": 17 }
```

`from`/`to` are character offsets into the original `function` string delimiting the offending
span (the whole string when a position cannot be localized). Both are `0` when valid. On error the
editor outlines the field in red, shows `error` below it, and marks the `from`..`to` span inline.

### Rules enforced (mirrored client-side for feedback)

The checks run in this order, and all mirror the backend exactly:

1. Length cap. The raw string must be at most 500 characters (`MAX_DISTANCE_FUNCTION_LENGTH`).
2. No `#` comments, and braces may only be bare `{name}` placeholders. A format spec, conversion,
   attribute, or index inside braces (`{value:>9}`, `{value!r}`, `{value.x}`, `{value[0]}`,
   `{0}`, `{}`), or an unbalanced `{`/`}`, is rejected.
3. Must parse as a single Python expression.
4. Node-count cap. At most 50 AST nodes (`_MAX_AST_NODES`).
5. Safe AST only:
   - Operators: `+ - * / // %`, unary `+ -`, bitwise `& |`, boolean `and or not`, and
     comparisons `== != < <= > >=`. Note `**` (power) is not allowed.
   - Numeric literals must be floats: write `3.0`, not `3`. Integer literals are rejected
     (arbitrary-precision bignum arithmetic is a DoS risk). Strings and bytes are rejected.
   - Calls are limited to `float`, `abs`, `min`, `max`, and `math.<fn>`. `int` is intentionally
     excluded, as are keyword arguments.
   - Allowed `math.*` functions: `exp expm1 log log1p log2 log10 sqrt pow fabs hypot sin cos tan
     asin acos atan atan2 sinh cosh tanh erf erfc degrees radians copysign fmod remainder`.
   - Allowed `math.*` constants: `pi e tau inf nan`. No other attribute access is permitted
     (blocks introspection escapes like `math.__loader__`).
6. Placeholders:
   - `{value}` and `{distance}` are always required.
   - Any name listed in the sibling `parameters` field is allowed (e.g. `parameters=["constant"]`
     permits `{constant}`), and declared parameters must appear in the function.
   - `{step_begin}` and `{step_end}` are runtime placeholders filled by BluePyEModel for the
     `step` distribution. They are always allowed but must not be added to `parameters`.
   - Any other placeholder (e.g. `{hello}`) is rejected as undeclared.

Placeholder validation updates live as `parameters` are added or removed, without editing the
function text.

### Example Pydantic implementation

The field **must** declare `max_length=MAX_DISTANCE_FUNCTION_LENGTH` (the same cap the backend
enforces), at the schema root. The schema test `validate_distance_function_input` (in
`tests/ui_schema/validate_block.py`) rejects any field whose `max_length` is missing or differs.

Used by concrete distributions whose `function` is a required `str` (e.g. the user-defined custom
distribution):

```py
class CustomDistanceDependentDistribution(DistanceDependentDistribution):
    title: ClassVar[str] = "Custom formula"
    function: str = Field(
        min_length=1,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Custom distance function",
        description="Python expression containing at least {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )
```

### UI design

(To be specified.)
