# 0002. Cut in chunks of space; the layout by morphology waits for a circuit that meets both its conditions

- Status: Accepted for chunks of space. The layout by morphology Deferred until a circuit meets both its conditions.
- Date: 2026-10-13, the user's word

## Context

A pack can be laid out two ways. By space: every placed cell's segments cut into cubes of the circuit, so a viewer fetches and culls what a view shows. By morphology: each distinct morphology once, in its own frame, and a cell as a morphology's number, a position and a rotation, which the circuit's node file already holds. The second is smaller where cells share morphologies, and leaves the cutting into chunks to the browser.

## Decision

Every pack is cut in chunks of space. `layout` in the index is `"space"`, the only value a reader takes today.

The layout by morphology is for a circuit whose cells' traced points are at least twice its distinct morphologies' (the reuse), and whose distinct morphologies hold at most 20M points. No circuit counted on 2026-10-13 met both, so it was not built.

## Alternatives weighed

Counted from node files and morphologies, 2026-10-13. Browser costs from the first review, one thread in Node and Chrome on the M4 Pro.

| Option | What it gave against chunks of space | Verdict |
| --- | --- | --- |
| A block a morphology, placed by the reader | No smaller where every cell has a morphology of its own. FlyWire's 139K morphologies would take the browser 42 s to its first picture and 4.0 min of a worker for the finer levels. | Deferred, for circuits that meet the rule |
| A block a cell | No sharing, and a view culls and fetches whole cells: a hex4-l4 cell spans 1,595 µm at the median. On the far level of the flat version 1 blocks, hex4 -1.5%, flywire-sugar +0.9%, beaten by larger chunks on every pack ([0010](0010-chunk-size.md)). | Rejected |
| The reuse rule, ≥ 2 and ≤ 20M points | FlyWire's reuse is 1.0, the 291 rat cells' 1.2, nbS1 Hex0's 1.28 by its files. Rat CA1 (6,213 cells) has 3.7, but its 1,584 morphologies hold 51M points. | Kept as the condition; no circuit meets it |

Under the rule, 20M points of shared morphologies are 27 to 46 MB to fetch and 12 to 23 s of one worker for the finer levels, which is why the second condition caps the library.

## Consequences

- The browser reads what a view shows and makes nothing: no levels, no cutting.
- A pack grows with the circuit's cells, not with its library. Shared morphologies are packed once a cell.
- Scaled copies of one reconstruction count as distinct: nbS1 Hex0's 23,444 files are 6,597 reconstructions, a reuse of 4.3 by those. A scale in the placement would fold them; not tried.
- Chunks cost bytes against a block a morphology, run starts above all; [0008](0008-run-starts-and-guessed-steps.md) and [0010](0010-chunk-size.md) take some of that back.
- The far level as blocks a morphology, which an overview fetches whole, stays open: FlyWire's estimated 135 to 164 MB in chunks against 96 MB so, before nesting. A read over a real network would settle it.
- The rule's third term, no pack over 212M traced points, went with [0001](0001-one-pack-built-by-obi-one.md)'s ceiling ([0017](0017-memory-cap.md)).
