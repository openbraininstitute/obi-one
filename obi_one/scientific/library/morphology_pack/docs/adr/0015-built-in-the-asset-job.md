# 0015. Built in the circuit asset job, last of its assets, at every scale under a segment cap; the endpoint is removed

- Status: Accepted. Replaces the on-request endpoint of [0001](0001-one-pack-built-by-obi-one.md).
- Date: 2026-10-22, the user's word

## Context

The pack was first built on request, in OBI-One's service, while the viewer waited ([0001](0001-one-pack-built-by-obi-one.md)). The service is one process on one task of 2 vCPU, 7,680 MiB in production and 3,584 MiB on staging, with 512 MiB of memory for temporary files. Its health is checked every 30 s and the task replaced after three misses. So the endpoint built one pack at a time, off the event loop, and refused a circuit over 5,000 neurons, 256 MiB of files or 5M points, or after two minutes' wait for another build. Most circuits a pack is for were refused before anything was read, and a stored pack ([0014](0014-stored-as-a-circuit-asset.md)) needs a writer with the right to add it.

Every way a circuit is registered passes one function that builds its other assets, either inline or in a launched job after validation.

## Decision

- The pack is one more asset of that step, built last, so the others are in if a job's time runs out while it builds. It is built where the circuit has none, or with `force`.
- Every circuit past a single neuron gets one ([0018](0018-no-pack-for-single-neurons.md)), whatever its scale, held to a cap on the segments of every level together. The cap follows the machine's memory ([0017](0017-memory-cap.md)).
- A task that registers circuits builds the pack inline where its machine is enough, as its other assets are. Otherwise the asset job builds it.
- The endpoint goes, with its limits, lock and settings. A circuit without a pack shows its somas until it has one.

## Alternatives weighed

| Option | What it gave against the chosen | Verdict |
| --- | --- | --- |
| On request, in the service | Works for any circuit a viewer can read, the day it ships. Bound by one request in one process: a few million points | Built first (2026-10-13), superseded here |
| On request, as a launched job | Fails for a public circuit seen from another project: only members of its project may add an asset | Rejected |
| A job of its own | A second launch for the same circuit, each beginning with a checkout and an install of some 150 packages | Rejected |
| At registration only | Circuits registered before get none | Rejected: the same step serves registration, the backfill and a rebuild with `force` |
| A gate by neuron count | Segments a neuron vary too much: FlyWire's 130,000 neurons can be under the cap and a rat model of 50,000 over it | Rejected for the segment cap |

## Consequences

- The pack's build is a library function from a circuit config on disk to bytes, or to the reason there are none. Fetching the circuit is the caller's business.
- Where the pack is the only asset missing, the job fetches only the circuit's config, nodes and the biophysical populations' morphologies, no edges.
- A circuit that can have no pack leaves no mark, so each call to rebuild its assets launches a job that builds nothing (the user, 2026-10-22: no marker for now).
- The circuits already registered get theirs by a backfill through the same step.
