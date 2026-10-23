# 0008. Run starts back-referenced, with the radius as a delta; each step guessed at three quarters of the one before

- Status: Accepted
- Date: 2026-10-19, the user's word

## Context

A run is a stretch of segments of one polyline that end in one chunk. Its first point is stored whole against the chunk's corner, about 13 bits an axis, since a start is spread evenly over the cube. In hex4-l4's flat version 1 blocks a run cost about 6.5 B of overhead, 26.3% of the far level's bytes at 4.0 segments a run. Yet at the finest level 53.7% of runs start at the x, y and z where an earlier run of the same cell in the chunk ends. And a fibre mostly goes on the way it went.

## Decision

- **Back-references.** A run that starts where an earlier run of its cell ends, within the chunk's cube, stores how many runs back that run is. Its x, y and z are that run's end; its radius step is stored as the difference from the end's. An end with the start's radius step is preferred. Other runs store their first point as before.
- **The guessed step.** After a run's first step, each step's x, y and z are stored less `floor((3 * s + 2) / 4)` of the step before, `(3 * s + 2) >> 2`. The radius step has no guess.

Both act on the runs a level holds of its own: all of the far level's, and those of the finer levels that follow no base segment ([0007](0007-levels-nested-over-their-base.md)). Both went into version 1 with nesting.

## Alternatives weighed

The flat version 1 blocks, before nesting: hex4-l4 at 188.32 MB of chunk blocks, Node, one thread, 2026-10-18 and 19.

| Option | hex4-l4 against the flat blocks | Verdict |
| --- | --- | --- |
| Start deltas from the run before, writer order (d1) | -0.9% | Rejected: smaller than the back-reference |
| Start deltas, runs by cell then Morton order (d3) | -1.2% | Rejected, as above |
| Morton order alone, with a signed cell stream (d2) | +0.8%, a loss | Rejected |
| Back-references with the same radius only (d4) | -3.9% | Rejected: d6 matches more runs |
| Back-references on x, y, z, the radius as a delta (d6) | -6.0% | Chosen |
| The guessed step at three quarters | -5.0% | Chosen |
| The whole step as the guess | worse on every level: -6.0 / -4.4 / -1.6% against -6.4 / -4.8 / -2.0% | Rejected |
| Deflate 9 on top | -0.7% | Rejected: the plane blocks of [0009](0009-deflate-blocks-per-byte-plane.md) beat it |

Measured over the nested blocks, with [0009](0009-deflate-blocks-per-byte-plane.md)'s block ends: d6 with the guess takes 15.72% off hex4-l4's far level and 12.42% off the middle level's runs of its own, where deflate 9 over the whole block takes 11.91% and 8.91%.

## Consequences

- Reading costs one shift and add an axis a segment and a lookup of a run's end: decoding with the expansion into arrays took 3.0% longer for d6 and 6.5% for the guess, in Node.
- The back-reference stream is two bytes wide in a chunk whose largest reference passes 255; a narrower encoding was not tried.
- The writer finds matching ends by sorting each chunk's run ends and starts by cell and point, in numpy. A prototype of the search and the guess took 4.4 s on hex4-l4's far level and the middle's own runs, against 2.5 s to encode them.
- A run refers only back, to a run before it in the chunk, so a reader rebuilds starts in one pass.
