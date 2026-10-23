# 0003. Positions on a 25 nm grid, radius on a log scale of 16 steps an octave

- Status: Accepted. A coarser grid and fewer radius steps Deferred until pictures at 64× are seen.
- Date: 2026-10-13

## Context

Floats deflate badly: their low bits look like noise to a coder. A pack stores whole numbers, so positions and radii need a step. The step sets the error and, through the size of each step from one point to the next, most of the bytes.

## Decision

A position is a whole number of `GRID_UM` = 0.025 µm steps, in the circuit's own frame: at most 12.5 nm off on an axis. Points are rounded first and the steps taken between rounded points, so the error does not add up along a branch.

A radius is a whole number of steps of a log scale, `RADIUS_STEPS` = 16 an octave: `2 ** (step / 16)` µm, within 2.2%. Radii under `SMALLEST_RADIUS_UM` = 1/1024 µm are raised to it.

One grid for the whole pack, written in the index as `gridUm` and `radiusSteps`.

## Alternatives weighed

Two bases. The first review: per-morphology packs of the 1,379-cell fly sample scaled to the whole brain (493 MB at 0.125 µm), deflate 9, 2026-10-13. The size measurements: the flat version 1 blocks, before nesting, hex4-l4 at 188.32 MB of chunk blocks, Node, 2026-10-18 and 19.

| Option | What it gave against 25 nm and 16 steps | Verdict |
| --- | --- | --- |
| Floats, x, y, z, radius and parent | 12.3 to 14.3 B a point deflated, against 9.7 to 9.8 for whole numbers on the grid, before steps (first review) | Rejected |
| 50 nm grid | First review -12%, 434 MB. Flat hex4 -9.7%, a position up to 25 nm an axis and 43.3 nm off. Over the nested stack the same share: hex4's 87.09 MB to 78.24 MB | Deferred: pictures at 64× not made |
| 100 nm grid | Flat hex4 -20.0%, 50 nm an axis off, 341 zero-length segments at the finest level | Rejected: twice the error, a product call |
| 8 radius steps an octave | First review -2%. Flat: hex4 -0.4%, CA1-300 -1.3%, flywire-sugar -3.1%. The radius up to 4.4% off | Deferred with the 50 nm grid |
| A grid per level, 250 nm on the far level | Flat hex4 -28.2% of the far level, -5.5% of the pack | Rejected: nesting needs one grid ([0007](0007-levels-nested-over-their-base.md)) |
| Offsets from the soma | +43% on the fly cells and +30% on the rat's (first review) | Rejected |

## Consequences

- A step from one point to the next mostly fits a byte at 25 nm. A cell twice as wide costs nothing more; a grid twice as coarse takes about 0.4 B a point off.
- The grid's rounding is a fifth of the finest level's tolerance of 0.125 µm ([0004](0004-simplification-tolerance.md)).
- A point shared by two levels must land on the same grid point at both, which nesting relies on. Points are turned and moved by sums of products, not a matrix product, which rounds a row by where it sits.
- A coarser uniform grid is a writer change alone: the reader takes `gridUm` from the index. A grid per level would be a reader change and is ruled out while levels nest.
