## Per neuron morphology location selection

ui_element: `per_neuron_morphology_location_selection`

This component selects exact points on exact neurons, for a configuration that targets more than
one neuron. Each selected point carries the neuron it belongs to, so one block can hold points
picked across several neurons without creating a cross-product between them.

It is the multi-neuron counterpart of `morphology_location_selection`. That element's row is a
`(section_id, offset)` pair, because the configuration it appears in targets a single implied
neuron, so there is nothing to disambiguate. Here the row carries a `node_id` as well, and the two
are deliberately separate elements rather than one element with an optional field: a SONATA node id
of `0` is a real neuron, so an absent-but-defaulted `node_id` could not be told apart from a
deliberate selection on the first neuron.

### Value

The value is an array of location rows. The field is required and the array must hold at least one
row (`minItems: 1`), so there is no empty or null state to represent: a block of locations that
selects nothing has no meaning. Each row has:

- `node_id`: the neuron the point sits on, a SONATA node id (integer, minimum 0).
- `section_id`: the SONATA global section id, `0` for the soma and neurites following in
  `nrn_order` (integer, minimum 0).
- `offset`: the normalized position along that section, `0.0` at its start and `1.0` at its end
  (number, 0.0 to 1.0).

For example:

```json
[
  {"node_id": 0, "section_id": 0, "offset": 0.0},
  {"node_id": 42, "section_id": 187, "offset": 0.5}
]
```

Each row is exactly one row of the generated `compartment_sets.json`, as
`[node_id, section_id, offset]`. Unlike the sampled morphology-location blocks, nothing is
expanded over a neuron set at materialization: the selected rows are written as they are.

Picking a point in a 3D view that renders more than one neuron identifies the neuron as part of the
same click, so `node_id` is expected to come from the selection rather than being typed in. The
`section_id` matches the `sonata_section_id` the viewer already receives for each rendered section,
so a stored row can be mapped back onto the morphology without a further lookup.

Reference schemas:
[per_neuron_morphology_location_selection](reference_schemas/per_neuron_morphology_location_selection.json)
and the row it references,
[NeuronMorphologyLocationPoint](reference_schemas/NeuronMorphologyLocationPoint.json)

### Example Pydantic implementation

```py
locations: Annotated[tuple[NeuronMorphologyLocationPoint, ...], Field(min_length=1)] = Field(
    title="Explicit locations",
    description=(
        "The exact points to target, each on a named neuron. Click anywhere on a neuron in "
        "the 3D view to add one, or type it in by hand. ... At least one point is required."
    ),
    json_schema_extra={
        SchemaKey.UI_ELEMENT: UIElement.PER_NEURON_MORPHOLOGY_LOCATION_SELECTION,
    },
)
```

where a row extends the single-neuron point with the neuron it belongs to:

```py
class NeuronMorphologyLocationPoint(MorphologyLocationPoint):
    """A neuron ID, SONATA global section ID and normalized offset defining one location."""

    node_id: NonNegativeInt = Field(
        title="Node ID",
        description="Identifier of the neuron this location belongs to.",
    )
```
