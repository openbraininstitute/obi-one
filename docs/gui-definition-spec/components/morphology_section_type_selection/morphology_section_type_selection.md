## Morphology section type selection

ui_element: `morphology_section_type_selection`

This component selects one or more morphology section categories. Options are populated from the
property endpoint identified by `property_group` and `property`.

This specification adds the backend and generated-schema contract only. The frontend still needs
to implement rendering and endpoint-driven option loading for this UI element.

The single backend property endpoint,
`/mapped-morphology-source-properties/{source_id}`, supports MEModel,
MEModel-with-synapses, and direct CellMorphology sources. Generated schema mappings retain the
frontend's workflow-specific placeholders (`{circuit_id}` or `{morphology_id}`); after substitution,
both resolve to this endpoint. The frontend does not currently support a source-neutral
`{source_id}` placeholder.

General Circuit support is deferred. It should be morphology-specific and reuse
`/circuit/viz/{circuit_id}/morphologies/{morphology_file}/section-types` once the UI can provide the circuit ID, morphology file, and optional morphology name. The property endpoint must not scan all morphologies in a circuit.

The component should render the returned options as checkboxes or a multi-select. Each option has:

- `value`: the integer section type stored in the configuration.
- `label`: the user-facing section type name.

For example:

```json
[
  {"value": 2, "label": "Axon"},
  {"value": 3, "label": "Basal dendrite"},
  {"value": 4, "label": "Apical dendrite"}
]
```

The property endpoint response contains the options under the field named by `property`:

```json
{
  "SectionTypes": [
    {"value": 2, "label": "Axon"},
    {"value": 3, "label": "Basal dendrite"},
    {"value": 4, "label": "Apical dendrite"}
  ]
}
```

The value supports both a single selection and parameter scans:

- `[2, 3, 4]`: one selection containing three section types.
- `[[2], [3, 4]]`: a scan with two selections.
- `null`: no section-type filter.

Reference schema:
[morphology_section_type_selection](reference_schemas/morphology_section_type_selection.json)

### Example Pydantic implementation

```py
section_types: tuple[int, ...] | list[tuple[int, ...]] | None = Field(
    default=None,
    title="Section types",
    description="Types of sections to generate locations on.",
    json_schema_extra={
        SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION,
        SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.MORPHOLOGY_SOURCE,
        SchemaKey.PROPERTY: MorphologySourceMappedProperties.SECTION_TYPES,
    },
)
```
