## Circuit neuronal manipulation by neuron

UIElement: `UIElement.ION_CHANNEL_VARIABLE_MODIFICATION_BY_NEURON`

This component backs `CircuitByNeuronMechanismVariableNeuronalManipulation`.

It extends the single-neuron (MEModel) "Full Neuron Variable Modification" block
for use in circuit simulations. The key difference: the **Neuron Set** dropdown is
visible, allowing the user to select which neurons the manipulation targets.

The available ion channel variables are the **intersection** of mechanism variables
across all emodels in the selected neuron set, fetched from the
`/neuronal-manipulation-properties` endpoint.

Reference schema:
[circuit_neuronal_manipulation_by_neuron](reference_schemas/circuit_neuronal_manipulation_by_neuron.json)

### UI design

<!-- TODO: Add screenshot -->

User flow:

1. Select a **Neuron Set** from the dropdown (targets for the manipulation).
2. The backend fetches the common mechanism variables for that neuron set.
3. Pick a channel + variable from the dropdown.
4. Enter one numeric value.

The variable picker is populated from the neuronal manipulation properties endpoint:

- `SchemaKey.PROPERTY_GROUP = "NeuronalManipulation"`
- `SchemaKey.PROPERTY = "MechanismVariablesByIonChannel"`

The endpoint requires the selected `neuron_set` as input to determine which
variables are available (intersection across all emodels in the selection).

### Example Pydantic implementation

```py
class CircuitByNeuronMechanismVariableNeuronalManipulation(
    ByNeuronMechanismVariableNeuronalManipulation,
):
    title: ClassVar[str] = "Full Neuron Variable Modification"

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
        },
    )

    # modification field is inherited from parent with:
    # SchemaKey.UI_ELEMENT: UIElement.ION_CHANNEL_VARIABLE_MODIFICATION_BY_NEURON
    # SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.NEURONAL_MANIPULATION
    # SchemaKey.PROPERTY: CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL
```

### Differences from MEModel variant

| Aspect | MEModel | Circuit |
|--------|---------|---------|
| Neuron Set field | Hidden (`UI_HIDDEN: True`) | Visible (`UIElement.REFERENCE`) |
| Variable source endpoint | `/mapped-circuit-properties/{id}` | `/neuronal-manipulation-properties` |
| Variables shown | All from the single emodel | Intersection across all emodels in neuron set |
| When data loads | On page load | After neuron set selection |

### Data model

Same as `ByNeuronModification` (inherited from parent):

- `ion_channel_id` (`uuid.UUID | None`): selected ion channel entity ID.
- `channel_name` (`str | None`): channel suffix for `conditions.mechanisms` key.
- `variable_name` (`str`): variable name to modify.
- `variable_type` (`"RANGE" | "GLOBAL"`, default `"GLOBAL"`): update mode.
- `new_value` (`float | list[float]`): value to apply.

### SONATA output

Same as parent. The `node_set` is resolved from the selected neuron set reference.

For **RANGE** variables:
```json
{
  "name": "modify_gSK_E2bar_SK_E2_all",
  "node_set": "Layer5_EXC",
  "type": "configure_all_sections",
  "section_configure": "%s.gSK_E2bar_SK_E2 = 0.002"
}
```

For **GLOBAL** variables:
```json
{
  "SK_E2": {
    "vmin_SK_E2": -80.0
  }
}
```
