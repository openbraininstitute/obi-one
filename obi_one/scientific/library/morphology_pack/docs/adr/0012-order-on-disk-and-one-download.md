# 0012. Coarsest first on disk, chunks from the middle out; one sequential download, range reads only if measured worth it

- Status: Accepted. Range reads Deferred until a sequential download is measured short.
- Date: 2026-10-21, the user's word; the order from the middle out 2026-10-22

## Context

A stored pack is fetched from object storage, and a viewer can draw while it downloads. Nested levels ([0007](0007-levels-nested-over-their-base.md)) mean a box can only be read once its base is in, and the far level is what a viewer draws first and keeps. The writer laid levels out finest first, so a stream showed nothing past the somas until the base, at the end of the file, came in.

| Pack, nested, 2026-10-19 | Size | Index and somas end at | The base |
| --- | --- | --- | --- |
| hex4-l4 | 80.65 MB | 0.134 MB | 31.23 MB, the last 39% |
| CA1-300 | 10.02 MB | 0.047 MB | 3.08 MB, the last 31% |
| hex6-l1 | 5.72 MB | 0.024 MB | 2.29 MB, the last 40% |

## Decision

- **Coarsest first.** After the header, the index and the somas come every level's chunks, the coarsest level first. The index's order of levels and their `base` numbers are unchanged; only the offsets move. hex4-l4's base now comes in from 0.06 MB on, not from 49 MB.
- **From the middle out.** Within a level, chunks are numbered by their box's distance from the middle of the box of the somas that have a position, nearest first, ties broken by place. The first view is framed near that middle.
- **One download.** A viewer fetches the whole pack in one sequential request and reads each box once its bytes are in.

A reader finds every block by its offset alone, so packs of any order read alike.

## Alternatives weighed

| Option | What it gave against the chosen | Verdict |
| --- | --- | --- |
| File order finest first | The somas at once, then nothing drawn until 61% of hex4-l4 is in | Rejected |
| Chunks in box order, x first | The base comes in as a slab sweeping across the circuit: hex4-l4's 31 MB base takes about 5 s at 50 Mbit/s | Rejected, 2026-10-22 |
| Range reads | Save only the finer levels a session never zooms into. Many requests, a cache of byte ranges, and a signed link to take again when it expires after 6 hours; the bucket does not expose `Content-Range` | Deferred: worth it only for packs over a browser cache's bound or slow links |
| A first-picture file, the segments seen from some 26 directions first | The outside of a whole fly brain from the first 5 to 10 MB, estimated, not measured | Not taken |

## Consequences

- In a browser on 2026-10-21, hex6-l1 sent at 1.5 MB/s then 300 KB/s: the pack's somas replaced the page's 1 s into a 19 s download, and the base swept in. The view at the end matched the view read from the cache to within one level of 255 in every pixel.
- A pack never changes under its asset id ([0014](0014-stored-as-a-circuit-asset.md)), so a viewer keeps it a month by its URL.
- Range reads would want neighbouring boxes near each other on disk, so that requests coalesce. Whether the middle-out order keeps them so, or Morton order would be needed, is for the range reads' own measures.
