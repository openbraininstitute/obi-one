# 0010. Chunks of 50 µm, doubled until there are at most 4,096

- Status: Accepted
- Date: 2026-10-13

## Context

A chunk is what a viewer fetches, culls and swaps a level for. Small chunks give a fine grain to all three, and cost bytes: each run starts whole, and a fibre crosses a small cube in few points. A circuit's extent varies from a few hundred micrometres to a whole fly brain, so a fixed size gives either too many chunks or too coarse a grain.

## Decision

A chunk is a cube of `CHUNK_UM` = 50 µm, 2,000 grid steps. The writer gathers the cubes every level's segments end in, and doubles the side until there are at most `MAX_CHUNKS` = 4,096 of them. The index gives the side as `chunkSteps`, the same at every level.

At first each level was doubled on its own. Since 2026-10-19 every level shares one size, so that a level is read over its base box by box ([0007](0007-levels-nested-over-their-base.md)).

In the flat version 1 packs the rule gave hex4-l4 200 µm chunks, hex6-l1 and CA1-300 100 µm, flywire-sugar 50 µm.

## Alternatives weighed

The flat version 1 blocks, before nesting: hex4-l4 at 188.32 MB of chunk blocks and 3,164 chunks a level, Node, one thread, 2026-10-18 and 19. Not measured with nesting.

| Option | hex4-l4 against today's rule | What it costs | Verdict |
| --- | --- | --- | --- |
| Chunks twice the side, 400 µm on hex4-l4 | -6.1%; hex6-l1 -9.1%, CA1-300 -9.8% | 615 boxes, culling 5 times coarser. The largest finest box 6.34 to 25.68 MB, the reader's buffers 68 to 286 MB | Not taken: the viewer's call |
| Four times the side | -7.4%; hex6-l1 -13.5%, CA1-300 -14.3% | 130 boxes, 24 times coarser. The largest box 36.58 MB, buffers 410 MB | Not taken, as above |
| A block a cell on the far level | -1.5% of the far level; flywire-sugar +0.9% | an index entry a cell, culling by a cell's span (1,595 µm at the median) | Rejected: four times the side beats it on every pack |

The first review estimated, on the 1,379-cell fly sample scaled to the whole brain, the finest level in 25 µm chunks at 36% over a block a morphology, 50 µm at 28% and 100 µm at 22%.

## Consequences

- A larger chunk saves bytes through fewer runs: each run removed saves about 10 B. That gain overlaps with the run-start levers of [0008](0008-run-starts-and-guessed-steps.md) and shrinks the gain of [0009](0009-deflate-blocks-per-byte-plane.md). Neither was measured together.
- `MAX_CHUNKS` is a writer setting. The reader derives every corner from `chunkSteps` and does not count on the bound.
- A wide, sparse circuit gets wide chunks: the bound is on their number, not their size.
- The order of the chunks on disk is [0012](0012-order-on-disk-and-one-download.md)'s.
