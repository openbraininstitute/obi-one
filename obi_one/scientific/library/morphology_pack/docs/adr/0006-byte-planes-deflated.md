# 0006. Streams of whole numbers as byte planes, deflated

- Status: Accepted for deflate. Another coder Deferred (the user's word, 2026-10-19: optional), reopened only if bytes still matter after nesting.
- Date: 2026-10-13, confirmed 2026-10-19

## Context

A chunk holds a few kinds of whole numbers: counts, steps on the grid, radius steps, cells and types. A coder gains most where numbers of one kind sit together and their high bytes, nearly all zero, sit apart from their low bytes. The browser has one inflater of its own, `DecompressionStream('deflate')`, in every browser; it has no zstd, and brotli only in Firefox and Safari.

## Decision

Each field of a chunk is a stream of its own. A stream is one byte giving the width of its numbers, 1 to 4 bytes, then every number's lowest byte, then every number's next byte, and so on. Signed numbers are zigzag. A chunk's streams are deflated together at `DEFLATE_LEVEL` = 6, in one zlib stream ([0009](0009-deflate-blocks-per-byte-plane.md)).

## Alternatives weighed

The format step by step, first review: the 1,379-cell fly sample, every point, deflate 9, bytes a point. A field a stream: 3.42. Byte planes: 2.97. A point a record of steps: 4.05.

The coders, on two bases. The first review: per-morphology packs of the fly sample scaled to the whole brain, 493 MB with deflate, read on one thread in Node. The size measurements: the flat version 1 blocks, before nesting, hex4-l4 at 188.32 MB of chunk blocks, Node, 2026-10-18 and 19.

| Option | First review | Flat hex4 | Read | Verdict |
| --- | --- | --- | --- | --- |
| zstd 19 | +1% | -4.1% | faster in Node; no browser decoder of its own | Deferred |
| brotli 11 | -1% | -9.2% | 1.68× in Node; WebAssembly in Chrome, 97.5 KB gzipped | Deferred |
| LZMA | -3% | | 8× | Rejected |
| bzip2 | +9% | | 10× | Rejected |
| Split streams by the step before | -8% | -2.9%, a loss on hex6-l1 and CA1-300 | 1.5× to 2.7× | Rejected |
| A context range coder | -10% | floor -11.1%, not built | 4× in JavaScript | Rejected: gains less than brotli over the run layout of [0008](0008-run-starts-and-guessed-steps.md) |
| meshopt records, then deflate | | -1.4%, nothing beyond zstd | 0.75× to 0.83× | Rejected: no Python encoder |
| HTTP content encoding | | | | Rejected: gzip, zstd and xz each made a fly pack larger |

Deflate is within 2% of the least any coder knowing only how often each number comes could reach (first review), and at the pooled zeroth-order entropy on hex4's flat finest and middle levels.

Over the nested pack, which is what ships: brotli is worth about 3 points, about 2 MB on hex4-l4, and zstd about nothing in bytes. Neither was measured on the additions blocks of [0007](0007-levels-nested-over-their-base.md).

## Consequences

- No dependency on either side: Python's zlib writes, the browser's own inflater reads.
- What a stream holds is the lever, not the coder: steps from the point before, nesting and run starts took far more than any coder ([0007](0007-levels-nested-over-their-base.md), [0008](0008-run-starts-and-guessed-steps.md)).
- Planes are what numpy writes in one call and what a reader takes apart without a branch.
- Another coder is reopened only if bytes still matter after nesting. It replaces deflate and the block ends of [0009](0009-deflate-blocks-per-byte-plane.md), not adds to them. Taken before the first deploy it stays version 1; after it, an older reader would misread the chunks, so the version goes up ([0013](0013-growing-the-format.md)).
