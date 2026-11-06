## Ion channel model properties

UIElement: `UIElement.ION_CHANNEL_MODEL_PROPERTIES` (one-off, used by `IonChannelFittingScanConfig.Initialize.model_properties`)

The properties an ion channel model is registered with, when it is fitted to several recordings at once: an object of five nullable properties. `null` means "take it from the recordings"; a value overrides the recordings, even when they agree.

| Property | Value | When `null` |
| --- | --- | --- |
| `ion_channel_name` | a NEURON identifier (`^[A-Za-z_][A-Za-z0-9_]*$`), the mod file `SUFFIX` | the recordings' channel name made NEURON-safe (`Kv6.2` gives `Kv6_2`) |
| `temperature` | a number, in °C | the recordings' temperature |
| `species` | `{"type": "SpeciesFromID", "id_str": ...}` | the recordings' species |
| `strain` | `{"type": "StrainFromID", "id_str": ...}`, of the model's species | the strain of the recordings of the model's species, if any |
| `brain_region` | `{"type": "BrainRegionFromID", "id_str": ...}` | the deepest region containing every recording's region |

When the recordings differ in the channel, temperature, species or strain and the property is `null`, generation fails with a `ConfigValidationError` naming the property.

The frontend reads the selected recordings from the sibling `recordings` field (a [model_identifier_multiple](../multiple_entities/multiple_entities.md)) to show what each `null` resolves to, and requires a value where they differ.

- Should be a `$ref` to an object with `additionalProperties: false` and an object `default`.
- Should have exactly the five properties above, plus `type`.
- Each property should have a `title` and a `description`, and be nullable with no default other than `null`.

Reference schema [ion_channel_model_properties](reference_schemas/ion_channel_model_properties.jsonc)

### Example Pydantic implementation

```py

class Initialize(Block):

    model_properties: IonChannelModelProperties = Field(
        default=IonChannelModelProperties(),
        title="Model properties",
        description="The channel name, temperature, species, strain and brain region the model is registered with.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.ION_CHANNEL_MODEL_PROPERTIES},
    )

```
