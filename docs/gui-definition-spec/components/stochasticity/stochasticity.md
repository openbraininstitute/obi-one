## Stochasticity

ui_element: `stochasticity`

A one-off element for the BluePyEModel `stochasticity` setting, whose value is a union
(``bool | tuple[str, ...]``):

- a **boolean** — enable or disable stochastic mechanisms globally, or
- a **list of protocol names** — enable stochastic mechanisms only for the named protocols.

The value must validate as a boolean or a list of strings, and nothing else. The schema is an
`anyOf` with a `boolean` branch and an array-of-strings branch.

### Custom behaviour

This element exists as a one-off because it needs custom rendering (a boolean toggle that can also
expand into a list of protocol names) that no generic element provides.

The protocol names are not free-form: they come from the protocols present in the selected
extraction result (see the task1 protocol catalogue). Rendering them as a constrained selection
requires a dynamic dropdown populated from that result, which depends on backend plumbing that
does not yet exist. Until then, the list entries are validated only by shape (a list of strings),
and constraining them to the available protocol names is a planned follow-up shared with the other
protocol-name fields (`validation_protocols`, `name_rin_protocol`, `name_rmp_protocol`,
`IV_curve_prot_name`, `FI_curve_prot_name`).

### Example Pydantic implementation

```py
class OptimizationSettings(Block):
    stochasticity: bool | tuple[str, ...] = Field(
        default=False,
        title="Stochasticity",
        description="Enable stochastic mechanisms globally or only for the listed protocol names.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STOCHASTICITY},
    )
```

### UI design

(To be specified.)
