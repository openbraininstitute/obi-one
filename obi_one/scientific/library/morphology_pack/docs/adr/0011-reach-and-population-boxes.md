# 0011. `reach` a chunk, and per-type population boxes in the index

- Status: Accepted
- Date: 2026-10-19 for `reach`, 2026-10-22 for the boxes

## Context

Two things a viewer needs before it reads a chunk were missing from the index.

Culling. A segment belongs to the chunk its far point lies in, so its near point may lie outside the cube. Nesting ([0007](0007-levels-nested-over-their-base.md)) made it worse: a segment that follows a base segment goes with the base's box, and a far segment at 1 µm spans far. Measured on hex4-l4's 200 µm cubes with the levels nested as planned, 4 to 5% of segments lie outside their box's cube, by up to 169.5 µm. The viewer grew each cube by a quarter of its side, 50 µm there.

Framing. The viewer framed a pack by its whole `bounds`. A pair or a small circuit opens with its axons hidden, and one long axon left the dendrites off-centre and small in the view.

## Decision

- **`reach`**, a number a chunk: how many grid steps its segments lie outside its cube at most, either end and any axis. A reader that culls by chunks grows each cube by it.
- **`boxes`**, a field of each population: for each section type its cells have (2 axon, 3 basal dendrite, 4 apical dendrite), the box of its points of that type at the finest level, in steps. A viewer frames the cells it shows by the boxes of their populations and of the types it draws. `bounds` is now the union of the boxes.

## Alternatives weighed

| Option | What it gave against the chosen | Verdict |
| --- | --- | --- |
| A larger fixed reach in the viewer | One margin for every chunk, as large as the worst chunk's: on hex4-l4, 169.5 µm round every 200 µm cube, so most boxes cull far coarser than their segments need | Rejected |
| The whole pack's bounds for framing | No new field. A view loose on the dendrites wherever axons are hidden or populations left out | Kept only as the fallback for packs without `boxes` |

## Consequences

- `reach` costs one number a chunk. It comes back from each chunk's encoding with its block.
- The boxes cost a polyline's box and a fold into one box a population and type: about 7 ns a point at pack time.
- `boxes` is optional: a pack written before it has none, and a reader then frames by `bounds`. It was the first field added under the rules of [0013](0013-growing-the-format.md), with no new version.
- Framing by the boxes of the types drawn opens a pair or small circuit centred and tight on its dendrites. Showing the axons does not reframe the view.
