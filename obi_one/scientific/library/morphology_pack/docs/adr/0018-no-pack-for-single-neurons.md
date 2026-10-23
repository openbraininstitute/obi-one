# 0018. No pack for single-neuron circuits, and no section ids in the format

- Status: Accepted
- Date: 2026-10-21

## Context

Pair and small circuits were drawn from a request a morphology, with exact sections and their section ids. Most simulations are set up on these circuits. Moving them onto the pack meant one data path for every circuit of two cells or more. What only the per-cell path does:

| Feature | Needs | Offered on |
| --- | --- | --- |
| Picking a morphology location, and its markers | section ids | single neurons and ME-models |
| Afferent synapses | exact sections, a distance field a cell | single neurons |
| Section-type colours of a lone cell | section types | a population of one cell |
| Axons hidden or shown | section types | single, pair, small |

The pack has every segment's section type, but not its section id. Simplification drops points, so a segment of the pack names no traced point: anything addressed by point needs the source, while sections hold.

## Decision

- Pair and small circuits are drawn from the pack, like larger ones. Hiding the axons reads the section type each segment already has.
- Single-neuron circuits, and ME-models, keep the per-cell path. A single-neuron circuit gets no pack: the viewer draws it from its morphology.
- The format holds no section ids.

## Alternatives weighed

| Option | What it gave against the chosen | Verdict |
| --- | --- | --- |
| Section ids as a stream a segment | Single neurons on the pack too. A new stream in every chunk, a change an older reader would misread ([0013](0013-growing-the-format.md)), and the synapses' distance fields rebuilt from pack segments | Rejected |

## Consequences

- A reader of the pack gets no section ids. That is why single-neuron circuits stay on their per-cell path.
- Morphology-location markers of a pair or small circuit's configuration are not drawn on the pack.
- Every circuit past a single neuron is built a pack ([0015](0015-built-in-the-asset-job.md)).
- A pair or small circuit with no pack yet is drawn a morphology a cell, as before.
- Picking a location, synapses and section ids stay on the per-cell path until a viewer needs them on circuits of many cells.
