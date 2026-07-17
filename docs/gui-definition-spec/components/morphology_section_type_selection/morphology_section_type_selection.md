## Morphology section type selection

ui_element: `morphology_section_type_selection`

This component selects one or more morphology section categories. Options are populated from the
property endpoint identified by `property_group` and `property`.

This specification adds the backend and generated-schema contract only. The frontend still needs
to implement rendering and endpoint-driven option loading for this UI element.

The single backend property endpoint,
`/mapped-morphology-source-properties/{source_id}`, supports MEModel,
MEModel-with-synapses, direct CellMorphology sources, and circuit sources up to microcircuit
scale. Single-neuron circuit sources are inspected directly. Pair, small, and microcircuit sources
return the static supported neurite options instead of scanning all morphologies in the circuit.
Generated schema mappings retain the frontend's workflow-specific placeholders (`{circuit_id}` or
`{morphology_id}`); after substitution, both resolve to this endpoint. The frontend does not
currently support a source-neutral `{source_id}` placeholder.

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
section_types: tuple[Literal[2, 3, 4], ...] | list[tuple[Literal[2, 3, 4], ...]] | None = Field(
    default=(2, 3, 4),
    title="Section types",
    description="Types of sections to generate locations on.",
    json_schema_extra={
        SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION,
        SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.MORPHOLOGY_SOURCE,
        SchemaKey.PROPERTY: MorphologySourceMappedProperties.SECTION_TYPES,
    },
)
```
