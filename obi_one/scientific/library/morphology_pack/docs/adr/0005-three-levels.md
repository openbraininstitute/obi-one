# 0005. Three levels: 0.125 µm, 0.25 µm, and 1 µm with twigs under 5 µm pruned

- Status: Accepted
- Date: 2026-10-13

## Context

A viewer draws a whole circuit far out and a few cells close up. Far out, a tube of the finest level is thinner than a pixel and its points cost memory and time for nothing. The viewer picks a level a chunk by the error the pixels would show, under a budget of segments in view, so it needs coarser levels than the finest.

## Decision

A pack holds three levels, finest first in the index (`LEVELS` in `geometry.py`):

| Level | `toleranceUm` | `pruneUm` |
| --- | --- | --- |
| Finest | 0.125 | 0 |
| Middle | 0.25 | 0 |
| Far | 1.0 | 5.0 |

The far level drops end branches shorter than 5 µm, unless alone on their fork, in one pass. It then joins end to end the sections that pruning leaves with one branch of their own type, and simplifies those.

The finest and middle levels come from one simplification pass; the far level from a second, over the same points.

## Alternatives weighed

The first review measured the levels on the 1,379-cell fly sample scaled to the whole brain, deflate, a block a morphology, and drew them on the M4 Pro, 2026-10-13.

| Option | What it gave against three levels | Verdict |
| --- | --- | --- |
| One level | The smallest file. A view of the whole brain then holds 146M points at 0.125 µm, 2.34 GB as segments on the GPU, or draws coarser than a close view wants | Rejected |
| Every point as a fourth level | 633 MB of the whole brain against 493 MB at 0.125 µm. At 0.0125 µm a pixel 10% of the pixels drawn differ, 7% not explained by a shift of a pixel | Rejected |
| Sticks, a segment a branch, twigs under 10 µm pruned | 29 MB for the whole brain against the far level's 96 MB, but a poor picture. The 1 µm level drawn as 1 px lines was faster in a whole-brain view of the fly sample placed 100 times, on the M4 Pro (9 to 12 ms a frame against 14 to 16) and truer | Rejected |
| A coarser far grid, 100 nm or 250 nm | The far level 96 to 75 MB at 100 nm (first review). 250 nm takes 28.2% off hex4-l4's far level in the flat version 1 blocks | Rejected: nesting needs one grid ([0003](0003-grid-and-radius-steps.md)) |
| A coarser far level, 2 µm and twigs under 10 µm, on a 250 nm grid | 40 MB for the whole brain against 96 MB | Not taken: open for the far view of the largest circuits |

## Consequences

- Each finer level is held over the next coarser one ([0007](0007-levels-nested-over-their-base.md)). The far level is the base a viewer reads first and keeps.
- The far level's segments are about 6 B each in hex4-l4's flat blocks, against 4.2 B at the finest: fewer points a run, so each costs more.
- A circuit of rat cells the size of nbS1 Hex0 (30,190 cells, 37.3M segments at the far level) fills a view far out with tubes under a pixel wide. A level coarser than 1 µm would serve it; none is built.
- Another set of levels is a writer change: the index lists the levels a pack has, each with its tolerance and pruning.
