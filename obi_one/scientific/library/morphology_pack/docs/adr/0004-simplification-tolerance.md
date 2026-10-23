# 0004. Ramer-Douglas-Peucker on path and diameter, the viewer's measure; the finest level at 0.125 µm, a setting of the build

- Status: Accepted
- Date: 2026-10-13

## Context

Traced morphologies hold many points in line, more so on rat cells than on fly cells. The GPU holds what is drawn, so every point dropped is memory saved. The morphology viewer already simplifies a cell before it meshes it: it drops the points of a section within half a voxel, 0.063 µm, of the path and the diameter, and resamples the axon to a point every 5 µm.

## Decision

Each level drops the points within its tolerance of the path and of the diameter: Ramer-Douglas-Peucker on x, y, z and twice the radius (`RADIUS_WEIGHT` = 2.0), section by section. It is the morphology viewer's measure, so a pack's finest level is what that viewer draws at the same tolerance. A section keeps both its ends at any tolerance.

The finest level's tolerance is 0.125 µm. It is a level's setting (`Level.tolerance_um`), written in its index entry as `toleranceUm`, so a reader knows what it holds. `LEVELS` in `geometry.py` sets it today; another tolerance is a pack built again.

The simplification runs in rounds: each round splits every open stretch of a morphology at its farthest point, one numpy pass a round, and records the largest tolerance each point survives. One pass serves every coarser level of the same pruning.

## Alternatives weighed

The first review: the 1,379-cell fly sample scaled to the whole brain (138,639 cells, 212M points), a deflate block a morphology on the 25 nm grid, M4 Pro, 2026-10-13. Outside: traced points farther from the simplified path than their radius.

| Option | Pack | Outside | Length kept | Verdict |
| --- | --- | --- | --- | --- |
| Every point | 633 MB | none | 100.0% | Rejected: size |
| 0.063 µm, the viewer's tolerance | 589 MB, -7% | 0.2% | 99.9% | Rejected: little saved on fly cells |
| 0.1 µm | 532 MB, -16% | 2.0% | 99.7% | Weighed, close second |
| 0.125 µm | 493 MB, -22% | 4.2% | 99.4% | Chosen |
| Path alone, 0.1 µm (morph_tool) | 473 MB, -25% | 3.1% | 99.5% | Rejected: 1 point in 100 off by 0.149 µm or more in radius, against 0.04 with the diameter held |
| A point every 5 µm | 173 MB, -73% | 67.1%, worst 2.19 µm | 88.2% | Rejected: a mesh's tool, not a pack's |
| Fewest points (Imai-Iri) | 481 MB, -2% | 5.8% | | Not taken: the rat cells' pack 8.5% smaller, about 60 lines in the build |

At 0.125 µm the worst traced point is 0.125 µm off the path and 99 in 100 are within 0.115 µm. The rat cells' pack is 48% smaller than every point.

## Consequences

- The far level, at 1 µm with pruning, comes from a second pass ([0005](0005-three-levels.md)); the finest and middle levels share one.
- Simplifying in rounds keeps the same points as the recursive loop at 290 to 360 ms a million points, against 4,029 ms for the loop with a numpy call a split (OBI-One's Python, one core of the M4 Pro).
- Close up a few beads are flattened, and 0.6% of the length is lost. Anything addressed by point number needs the source: points are not the file's by number.
- The fewest points would spend more of the tolerance for the same test: 20% of the rat's traced points outside their tube where 9.5%.
