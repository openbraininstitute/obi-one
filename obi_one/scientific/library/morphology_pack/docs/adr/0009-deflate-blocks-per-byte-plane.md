# 0009. Deflate blocks end at every byte plane, Z_FILTERED, on blocks over 1 KB

- Status: Accepted
- Date: 2026-10-19

## Context

A chunk's streams were deflated as one zlib stream ([0006](0006-byte-planes-deflated.md)). Deflate then shares its Huffman tables across planes of very different bytes: a high plane nearly all zero, a low plane nearly uniform. zlib cuts a large block into deflate blocks of about 16K symbols on its own, so the gain lies in the chunks of 1 to 256 KB. Ending a deflate block is a writer's choice: any inflater reads the result, so it needs no reader change.

## Decision

A chunk's block over `PLAIN_DEFLATE_BYTES` = 1,024 bytes inflated is one zlib stream at `DEFLATE_LEVEL` = 6, the filtered strategy (`Z_FILTERED`), whose deflate blocks end at every byte plane (`flush(Z_BLOCK)`). Each plane gets Huffman tables of its own, while the window carries across. A block of 1 KB or less is deflated whole at level 6.

## Alternatives weighed

The flat version 1 blocks, before nesting: hex4-l4 at 188.91 MB of chunk blocks, the writer's own zlib against itself, Python, 2026-10-18 and 19.

| Option | hex4-l4 | Writer's time against level 6 | Verdict |
| --- | --- | --- | --- |
| Deflate 9, whole | -0.7% | 4.2× to 6.7× | Rejected |
| A block a stream | -0.84% | | Rejected: the planes' own tables are worth 1.2 to 2.3 points more |
| A block a byte plane | -2.32% | 1.03× to 1.05× | Rejected: Z_FILTERED adds to it |
| A block a plane, Z_FILTERED | -2.91% | 1.03× to 1.14× | Rejected: small chunks lose |
| The same over 1 KB, plain under | -2.98%, -5.63 MB | as above | Chosen |
| The same over 16 KB | no better than a block a plane on most levels | as above | Rejected |
| The same at level 9 | -3.77% | 4.2× to 6.7× | Rejected: the writer's time |
| Sync or full flush in place of Z_BLOCK | 4 to 5 B a boundary, about 52,700 boundaries a level | | Rejected |
| Huffman only | smaller on hex6-l1's and CA1-300's far levels, larger on the finest | inflate 12 to 66% slower | Rejected |

A block of 1 KB or less loses about 1.25 B a boundary: the block header and end symbol. That sets the cut.

## Consequences

- As built, the flat packs: hex4-l4 189.03 to 183.39 MB (-3.0%), hex6-l1 -5.7%, CA1-300 -4.0%, flywire-sugar -3.9%. Every chunk of the four inflated through `DecompressionStream('deflate')`, in Node, to the same bytes.
- On the nested blocks of [0007](0007-levels-nested-over-their-base.md), hex4-l4: -2.15% off the middle additions, -3.06% off the finest additions, -5.76% off the middle level's runs of its own, against deflate 6 whole.
- The gain grows as chunks shrink and levels coarsen, and shrinks with larger chunks ([0010](0010-chunk-size.md)).
- Bytes depend on the writer's zlib build; the reader does not. Another coder would replace this, not add to it ([0006](0006-byte-planes-deflated.md)).
