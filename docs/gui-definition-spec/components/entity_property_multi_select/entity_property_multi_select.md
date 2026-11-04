## Entity property multi select

ui_element: `entity_property_multi_select`

Chooses any number of an entity's own items, such as the channels of a recording. Unlike a sweep, the chosen items together make one value.

- Should accept a list of strings, which may be empty and is not a scan dimension. In Pydantic, that is a `tuple[str, ...]`.
- Should have the following non-validating properties:
    - `property_group` (str): A key of the parent scan config's `property_endpoints`, whose endpoint returns the `property dictionary`.
    - `property` (str): The key to use from the `property dictionary`. Its value should be a list of `{"value": str, "label": str}`, where `value` is what is stored and `label` what the user reads and searches.

Reference schema [entity_property_multi_select](reference_schemas/entity_property_multi_select.jsonc)

### Example Pydantic implementation

```py
class Initialize(Block):

    channels_to_ignore: tuple[str, ...] = Field(
        default=(),
        title="Channels to ignore",
        description="Channels removed before any processing.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_MULTI_SELECT,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.EXTRACELLULAR_RECORDING,
            SchemaKey.PROPERTY: ExtracellularRecordingMappedProperties.CHANNELS,
        },
    )
```

### UI design

A searchable multiple-choice dropdown, empty by default, which does not choose anything on its own. A stored value the entity no longer has is shown as such.
