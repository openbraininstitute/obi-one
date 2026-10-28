# Morphology-location preview

Parametric morphology-location blocks (random, clustered, path-distance) only produce concrete
points once they are evaluated against a morphology. This endpoint runs that evaluation on its own,
so the 3D viewer can show where the points land before the workflow is launched.

## Endpoint

```
POST /declared/morphology-locations/preview/{entity_id}
```

`entity_id` is an MEModel, a cell morphology, or a single-neuron circuit — the same sources the
viewer already renders. A multi-neuron circuit is rejected: it does not identify which morphology
to preview without a node id.

The body is a single morphology-location block, in the same form it takes inside a scan config:

```json
{
  "type": "RandomMorphologyLocations",
  "random_seed": 0,
  "number_of_locations": 20,
  "section_types": [3, 4]
}
```

The response is the generated locations:

```json
{
  "locations": [
    {"section_id": 187, "offset": 0.42},
    {"section_id": 203, "offset": 0.87}
  ]
}
```

## Reading the response

`section_id` is a SONATA global section id: `0` is the soma, neurites follow in NEURON section
order. It matches the `sonata_section_id` the viewer already receives for each rendered section, so
a location can be placed without another lookup. `offset` is normalized along that section, `0.0` at
its start and `1.0` at its end.

These are the same two values the block writes to `compartment_sets.json` when the workflow runs.
The node id of each persisted row is not part of the preview: it comes from the neuron set the block
is applied to, which a single-morphology preview does not have.

## What a preview does and does not promise

Generation is deterministic for a given morphology and seed, so previewing a block and then running
it places the points in the same spots.

It follows that changing `random_seed` moves them, and that a preview against one morphology is
representative rather than exact for a multi-neuron target: applied to a neuron set, the block
samples every targeted morphology independently, and the same section id means a different branch on
each one.

## Errors

| Status | Cause |
| --- | --- |
| 404 | `entity_id` is not an MEModel, cell morphology, or single-neuron circuit |
| 422 | a parameter is still a sweep list, or the block cannot be evaluated on this morphology |

Sweeps are rejected before the morphology is resolved, so an unusable request costs no download.
