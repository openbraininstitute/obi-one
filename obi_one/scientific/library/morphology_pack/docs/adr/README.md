# Decisions

| # | Decision | Status | Date |
| --- | --- | --- | --- |
| 0001 | [Morphologies reach the viewer as one binary pack built by OBI-One](0001-one-pack-built-by-obi-one.md) | Accepted in part; the endpoint superseded by 0015, the ceiling by 0017 | 2026-10-13 |
| 0002 | [Cut in chunks of space; the layout by morphology waits for a circuit that meets both its conditions](0002-chunks-of-space.md) | Accepted; the layout by morphology Deferred | 2026-10-13 |
| 0003 | [Positions on a 25 nm grid, radius on a log scale of 16 steps an octave](0003-grid-and-radius-steps.md) | Accepted; a coarser grid and fewer radius steps Deferred | 2026-10-13 |
| 0004 | [Ramer-Douglas-Peucker on path and diameter, the viewer's measure; the finest level at 0.125 µm, a setting of the build](0004-simplification-tolerance.md) | Accepted | 2026-10-13 |
| 0005 | [Three levels: 0.125 µm, 0.25 µm, and 1 µm with twigs under 5 µm pruned](0005-three-levels.md) | Accepted | 2026-10-13 |
| 0006 | [Streams of whole numbers as byte planes, deflated](0006-byte-planes-deflated.md) | Accepted for deflate; another coder Deferred | 2026-10-13, confirmed 2026-10-19 |
| 0007 | [Each level held as additions over its base, the chord's guess for inner points, in version 1](0007-levels-nested-over-their-base.md) | Accepted | 2026-10-19 |
| 0008 | [Run starts back-referenced, with the radius as a delta; each step guessed at three quarters of the one before](0008-run-starts-and-guessed-steps.md) | Accepted | 2026-10-19 |
| 0009 | [Deflate blocks end at every byte plane, Z_FILTERED, on blocks over 1 KB](0009-deflate-blocks-per-byte-plane.md) | Accepted | 2026-10-19 |
| 0010 | [Chunks of 50 µm, doubled until there are at most 4,096](0010-chunk-size.md) | Accepted | 2026-10-13 |
| 0011 | [`reach` a chunk, and per-type population boxes in the index](0011-reach-and-population-boxes.md) | Accepted | 2026-10-19 and 2026-10-22 |
| 0012 | [Coarsest first on disk, chunks from the middle out; one sequential download, range reads only if measured worth it](0012-order-on-disk-and-one-download.md) | Accepted; range reads Deferred | 2026-10-21 and 2026-10-22 |
| 0013 | [Rules for growing the format; the version goes up only for a change an older reader would misread](0013-growing-the-format.md) | Accepted | 2026-10-22 |
| 0014 | [Stored as the circuit's `circuit_morphology_pack` asset, `.mpack`, `application/octet-stream`](0014-stored-as-a-circuit-asset.md) | Accepted | 2026-10-21, changed 2026-10-22 |
| 0015 | [Built in the circuit asset job, last of its assets, at every scale under a segment cap; the endpoint is removed](0015-built-in-the-asset-job.md) | Accepted | 2026-10-22 |
| 0016 | [Simplification and encoding over a process pool of at most 8; the same bytes on any number](0016-process-pool.md) | Accepted | 2026-10-19 |
| 0017 | [The build's memory cap from the container's limit, with `MAX_SEGMENTS` at 300M; job sizes by scale, 16 GB past a microcircuit](0017-memory-cap.md) | Accepted; a writer through disk Deferred | 2026-10-23 |
| 0018 | [No pack for single-neuron circuits, and no section ids in the format](0018-no-pack-for-single-neurons.md) | Accepted | 2026-10-21 |

Each file gives a status and the day the decision was made, then its context, the decision, the alternatives weighed in a table of what each gave against the one chosen and on which pack it was measured, and the consequences. A status is Accepted, Superseded by another decision, or Deferred, and a decision can be Accepted with a part Deferred or superseded; the date is the decision's own, with "the user's word" where the user made it.
