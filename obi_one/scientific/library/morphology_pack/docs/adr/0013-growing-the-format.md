# 0013. Rules for growing the format; the version goes up only for a change an older reader would misread

- Status: Accepted
- Date: 2026-10-22

## Context

Packs are stored as circuit assets ([0014](0014-stored-as-a-circuit-asset.md)) and outlive the code that wrote them. Readers are deployed apart from the writer: a viewer in the browser, and `reader.py`. Before the first deploy every change went into version 1, since no pack had been served ([0007](0007-levels-nested-over-their-base.md)). The first new field of the index after that, per-type boxes for framing ([0011](0011-reach-and-population-boxes.md)), needed a rule for what a new field does to packs already written and readers already deployed.

## Decision

- Something new about a pack is an optional field of the index. Its absence means it is not known, and a reader does without it, as it did before.
- A reader ignores the fields of the index it does not know.
- Something too large for the index is a block of its own, found by an offset and a length in the index, as `somas` is.
- A field keeps its meaning. Another meaning is another field.
- The version goes up only for a change a reader of the version before would misread, such as a chunk's encoding or a unit. A reader refuses a version it does not know.

The header holds the version as a uint16, `VERSION` = 1 today. `take_apart` refuses a pack of another version or another magic.

## Alternatives weighed

| Option | What it gave against the rules | Verdict |
| --- | --- | --- |
| A version for every change | Every older reader refuses every newer pack, and a viewer falls back to somas for a field it could have done without. Every stored pack is rebuilt for each change | Rejected |

A case the rules decide: a grid per level ([0003](0003-grid-and-radius-steps.md)) changes what a step means on one level. A reader that ignores the new field would read that level at the wrong scale rather than refuse it, so it needs a new version.

## Consequences

- `PopulationEntry.boxes` defaults to None, and a pack without it is framed by `bounds`.
- A reader that validates the index must let unknown fields through or drop them, never fail on them.
- A change that does need a new version means every stored pack is rebuilt, or readers keep reading the older version beside the new.
- Another coder ([0006](0006-byte-planes-deflated.md)) taken after the first deploy is such a change.
