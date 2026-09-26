## Distance function input

ui_element: `distance_function_input`

A single-line editor for a distance-dependent distribution `function`: a math expression that
BluePyEModel evaluates per morphology segment (e.g. `math.exp((-{distance})/50)*{value}`). It
behaves like [string_input](../string/string_input.md) (the stored type is `string`), but the UI
renders a code editor that validates the expression live and shows errors inline.

The type should be `string` (or `string | None` on the abstract base). It is used by the custom
and built-in distance-dependent distributions in the EModel optimisation config.

### Why this is a distinct element

The function string is user-controlled and reaches Python `eval()` at runtime, so it is a code
injection surface. obi-one enforces a safe whitelist server-side (see
`validate_safe_distance_function`); this element tells the UI to run the **same** whitelist
client-side for instant feedback. The backend remains the security boundary, the client check is
a convenience layer only.

The editor enforces two rules, mirroring the backend:

1. Safe AST only. The expression may use arithmetic and comparison operators, numeric literals,
   `math.*` functions, and the builtins `int`, `float`, `abs`, `min`, `max`. Anything else (bare
   names like `a`, attribute access outside `math`, arbitrary calls like `os.system(...)`,
   subscripts, etc.) is rejected.
2. Allowed placeholders only. `{value}` and `{distance}` are always allowed and required. Any
   name listed in the sibling `parameters` field is also allowed (e.g. declaring
   `parameters=["constant"]` permits `{constant}`). Unknown placeholders like `{hello}` are
   rejected. Placeholder validation updates live as `parameters` are added or removed, without
   editing the function text.

On error the editor outlines the field in red, shows a message below it, and marks the offending
span inline.

### Example Pydantic implementation

```py
class CustomDistanceDependentDistribution(DistanceDependentDistribution):
    function: str = Field(
        min_length=1,
        title="Custom distance function",
        description="Python expression containing at least {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )
```

### UI design

(To be specified.)
