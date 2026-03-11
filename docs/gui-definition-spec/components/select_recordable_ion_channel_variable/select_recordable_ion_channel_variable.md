## ion channel recordings dropdown

ui_element: `docs/gui-definition-spec/components/select_recordable_ion_channel_variable`


This component backs `IonChannelVariableRecording`.

Use it to select a recording present among the ion channel models selected.

Reference schema: ...

### UI design

<img src="design/docs/gui-definition-spec/components/select_recordable_ion_channel_variable.png" width="430" />

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
            "ui_element": "docs/gui-definition-spec/components/select_recordable_ion_channel_variable",
            "property_group": EntityType.IONCHANNELMODEL,
            "property": IonChannelPropertyType.RECORDABLE_VARIABLES,
        },
    )
```

### Data model (`IonChannelVariable`)

- `ion_channel_id` (`uuid.UUID | str | None`): selected ion channel entity ID (if applicable).
- `variable_name` (`str`): variable name to record.
- `channel_name` (`str`): the SUFFIX of the channel in the hoc file
