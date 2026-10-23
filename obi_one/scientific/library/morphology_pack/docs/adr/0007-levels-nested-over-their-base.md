# 0007. Each level held as additions over its base, the chord's guess for inner points, in version 1

- Status: Accepted
- Date: 2026-10-19, the user's word

## Context

The three levels ([0005](0005-three-levels.md)) were written whole, each level's chunks standing alone. Yet every point of the middle level is a point of the finest, at the same position and radius step, and almost every point of the far level is a middle point. A viewer that zooms in already holds the coarser level of a box when it asks for the finer one. No pack had been served yet, so a change of format did not need a new version.

## Decision

A level is read over its base, the next coarser level, chunk by chunk in the same box. Where the finer level runs along a base segment, from its near point to its far point through points of its own, it holds only how many segments follow it and those inner points. The rest are runs of its own. The coarsest level holds runs only.

An inner point is stored against the chord's guess: `p + floor((q - p) / left)` for each of x, y, z and radius step, where `p` is the point before, `q` the base segment's far point and `left` the segments still to come.

The finest and middle levels come from one simplification pass and the far level walks the same points, so the writer finds the followers by index. A far segment is followed only where no branch along its way starts apart from its fork, in position or width.

All of it went into version 1 before the first deploy (the user's word, 2026-10-19). Where the measurements of the time say "version 2", they mean a reader change, which shipped with the writer.

## Alternatives weighed

The flat version 1 blocks, before nesting: hex4-l4 at 188.32 MB of chunk blocks. Node, one thread, M4 Pro, 2026-10-18 and 19.

| Option | hex4-l4 against the flat blocks | Verdict |
| --- | --- | --- |
| Levels sent whole | 188.32 MB | Rejected |
| Finest level only over the middle, plain | -31.9% | Rejected: the middle and far levels stay whole |
| Finest level only, chord | -34.4% | Rejected, as above |
| Three levels nested, plain | -48.3%, 97.42 MB | Rejected: the chord costs nothing to read |
| Three levels nested, chord | -53.8%, 87.09 MB | Chosen |

The chord's stack on the other packs: hex6-l1 -54.4%, CA1-300 -50.6%, flywire-sugar -48.8%. Every segment matched one to one on hex4-l4 after the rebuild.

What it costs to read, the same decoder on both sides, hex4-l4: a finest box read cold fetches 1.15 times the bytes and decodes in 1.53 times the time. The viewer's zoom path, the far level held and the middle kept, fetches 0.40 times and decodes in 0.63 times. The chord reads within 2% of plain.

## Consequences

- As built, CA1-300 went from 20.74 MB to 10.02 MB, -51.7%, every level reading back to the same segments; 99.43% of its far segments are followed. hex4-l4, rebuilt with the shipped levers of that day, is 80.65 MB, from 189.03 MB flat.
- A segment that follows a base segment goes with the base's box and may lie far outside its own cube: [0011](0011-reach-and-population-boxes.md) adds `reach`.
- One grid for every level ([0003](0003-grid-and-radius-steps.md)), and a point shared by two levels lands on the same grid point at both.
- Every level shares one chunk size ([0010](0010-chunk-size.md)), and a reader must have a box's base before the box: [0012](0012-order-on-disk-and-one-download.md) puts the bases first on disk.
- The run levers of [0008](0008-run-starts-and-guessed-steps.md) now act on the far level and on each level's own runs only.
