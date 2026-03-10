## ion channel recordings dropdown

ui_element: `ion_channel_recordings_dropdown`


This component backs `IonChannelVariableRecording`.

Use it to select a recording present among the ion channel models selected.

Reference schema: ...

### UI design

<img src="design/ion_channel_recordings_dropdown.png" width="430" />

Placeholder for design: it would be like the Manipulations design, but without the location (soma, axon, etc.)

User flow:

1. Pick a channel + variable from the dropdown.

The variable picker is populated from mapped ion channel models properties using:

- `property_group = "IonChannelModel"`
- `property = "RecordedVariables"`

### Example Pydantic implementation

```py
class IonChannelVariableRecording(Recording):
    title: ClassVar[str] = "Ion Channel Variable Recording (Full Experiment)"

    variable: IonChannelVariable = Field(
        title="Ion Channel Variable Name",
        description="Name of the variable to record with its unit, "
        "grouped by ion channel model name.",
        json_schema_extra={
            "ui_element": "ion_channel_recordings_dropdown",
            "property_group": EntityType.IONCHANNELMODEL,
            "property": IonChannelPropertyType.RECORDABLE_VARIABLES,
        },
    )
```

### Data model (`ByNeuronModification`)

- `ion_channel_id` (`uuid.UUID | str | None`): selected ion channel entity ID (if applicable).
- `variable_name` (`str`): variable name to record.
- `unit` (`str`): Unit of the variable (e.g., 'mA/cm2', 'mV', 'mM').
