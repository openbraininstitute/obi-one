## Entity property multi select

ui_element: `entity_property_multi_select`

- Should accept a list of `string`s as input: **one value** that is a list, not a
  parameter sweep. (`entity_property_dropdown` on a `str | list[str]` field also lets
  the user pick several values, but obi-one expands those into a scan dimension.)
- Should have the following non-validating properties:
    - `property_group` (str): The name of a key for which there is a corresponding key in
      the `property_endpoints` dictionary of the parent scan config. Its value references
      an endpoint returning a `property dictionary`.
    - `property` (str): the key to use from the `property dictionary`. Its value must be a
      list of strings: the options the user can pick from.
- The UI shows a multi-select restricted to those options and writes the selected
  options, in the order of the options list, as the field's value. A stored value that
  is not among the options is shown and flagged rather than dropped silently.

Reference schema [entity_property_multi_select](reference_schemas/entity_property_multi_select.json)

### Example Pydantic implementation

```py
class Settings(Block):

    rheobase_protocols: tuple[str, ...] = Field(
        default=("IDThreshProtocol",),
        min_length=1,
        title="Rheobase protocols",
        description="Protocols whose sweeps give each recording's rheobase.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_MULTI_SELECT,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.ELECTRICAL_CELL_RECORDINGS,
            SchemaKey.PROPERTY: ElectricalCellRecordingMappedProperties.RHEOBASE_PROTOCOLS,
        },
    )
```

A `tuple` (not a `list`) keeps the obi-one scan framework from treating the value as a
scan dimension.

### UI design

No design yet: a multi-select variant of the
[entity_property_dropdown](../entity_property_dropdown/entity_property_dropdown.md).
