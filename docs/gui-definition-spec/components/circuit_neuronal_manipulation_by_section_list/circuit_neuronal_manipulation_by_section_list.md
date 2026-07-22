## Circuit neuronal manipulation by section list

UIElement: `UIElement.ION_CHANNEL_VARIABLE_MODIFICATION_BY_SECTION_LIST`

This component backs `CircuitBySectionListMechanismVariableNeuronalManipulation`.

It extends the single-neuron (MEModel) "Variable Modification by Section List" block
for use in circuit simulations. The key difference: the **Neuron Set** dropdown is
visible, allowing the user to select which neurons the manipulation targets.

The available ion channel variables are the **intersection** of mechanism variables
across all emodels in the selected neuron set, fetched from the
`/neuronal-manipulation-properties` endpoint.

Reference schema:
[circuit_neuronal_manipulation_by_section_list](reference_schemas/circuit_neuronal_manipulation_by_section_list.json)

### UI design

<!-- TODO: Add screenshot -->

User flow:

1. Select a **Neuron Set** from the dropdown (targets for the manipulation).
2. The backend fetches the common mechanism variables for that neuron set.
3. Pick a channel + variable from the dropdown.
4. Enter one value per section list shown by the UI.

The variable picker is populated from the neuronal manipulation properties endpoint:

- `SchemaKey.PROPERTY_GROUP = "NeuronalManipulation"`
- `SchemaKey.PROPERTY = "MechanismVariablesByIonChannel"`

The endpoint requires the selected `neuron_set` as input to determine which
variables are available (intersection across all emodels in the selection).

### Example Pydantic implementation

```py
class CircuitBySectionListMechanismVariableNeuronalManipulation(
    BySectionListMechanismVariableNeuronalManipulation,
):
    title: ClassVar[str] = "Variable Modification by Section List"

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
    # SchemaKey.UI_ELEMENT: UIElement.ION_CHANNEL_VARIABLE_MODIFICATION_BY_SECTION_LIST
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

Same as `BySectionListModification` (inherited from parent):

- `ion_channel_id` (`uuid.UUID | None`): selected ion channel entity ID.
- `variable_name` (`str`): RANGE variable name to modify.
- `section_list_modifications` (`dict[str, float | list[float]]`):
  mapping of section list to value.

### SONATA output

Same as parent. The `node_set` is resolved from the selected neuron set reference.

```json
[
  {
    "name": "modify_gSK_E2bar_SK_E2_somatic",
    "node_set": "Layer5_EXC",
    "type": "section_list",
    "section_configure": "somatic.gSK_E2bar_SK_E2 = 0.002"
  }
]
```
