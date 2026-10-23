# 0017. The build's memory cap from the container's limit, with `MAX_SEGMENTS` at 300M; job sizes by scale, 16 GB past a microcircuit

- Status: Accepted. Replaces the ceiling of 212M traced points of [0001](0001-one-pack-built-by-obi-one.md). A writer through disk (Phase 3) Deferred.
- Date: 2026-10-23, the user's word

## Context

A build holds every level of every cell in memory until it packs them. A build that outgrows its container is killed by the kernel, which no `try` catches: the whole asset task fails. The first ceiling, 212M traced points, counted the circuit before simplification and knew nothing of the machine. On 2026-10-22 the cap became the memory left at a flat 100 B a segment, which held a 16 GB job to about 165M segments.

Measured in a Linux container held to 2 CPUs with no swap, on the memory that cannot be reclaimed, after the memory work of 2026-10-23 (every pack the same to the byte):

| Build | Peak before | After |
| --- | --- | --- |
| CA1, 1,500 cells, 23.5M segments | 1,458 MB | 1,346 MB |
| CA1, 3,000 cells, 46.8M segments | 2,384 MB | 2,074 MB |
| 1,584 cells, one morphology each, 36.7M segments | 2,475 MB | 1,984 MB |

A fit above what the process held at the start: 299 MB and 40.3 B a segment where cells share their morphologies, 286 MB and 43.3 B where none share one. Each process past two held about 110 MB more while simplifying.

## Decision

The segments a pack may hold, every level together, are the lesser of `MAX_SEGMENTS` = 300M and

`(memory left - BASE_BYTES - BYTES_A_WORKER × (processes - 2)) // BYTES_A_SEGMENT`

with `BASE_BYTES` = 400 MiB, `BYTES_A_WORKER` = 128 MiB, `BYTES_A_SEGMENT` = 50. The memory left is the cgroup's limit, v2 or v1, or the machine's memory, less what the process holds once its freed memory is handed back. The build stops at the first morphology that takes the levels past it. The log says which of the two decided.

The asset job's machine follows the circuit's scale, an hour each:

| Scale | Cores | Memory | Cap |
| --- | --- | --- | --- |
| single, pair, small | 1 | 4 GB | about 70M |
| microcircuit, or none | 2 | 16 GB | 300M |
| region, system, whole brain | 4 | 16 GB | 300M |

## Alternatives weighed

| Option | What it gave against the chosen | Verdict |
| --- | --- | --- |
| 212M traced points, [0001](0001-one-pack-built-by-obi-one.md)'s ceiling | Counts the circuit, not the build. nbS1 Hex0 (334M points) refused whatever the machine | Replaced |
| `MAX_SEGMENTS` at 600M, as the cap model was first built on 2026-10-23 | Larger circuits packed on larger machines; a pack past 300M is several GB for the viewer to fetch and hold | Rejected, kept at 300M, the user's word |
| 30 GB past a microcircuit | Nothing more: 16 GB holds 300M on four processes as on two | Rejected, the user's word |
| A writer through disk (Phase 3) | Memory bound by a group of chunks, not the circuit: would carry a 30,000-cell CA1 slice (about 470M segments, estimated) on 16 GB. A writer rewrite, about 20 B a segment of temporary disk, time unmeasured | Deferred |

## Consequences

- The whole FlyWire brain, about 255M segments, fits under `MAX_SEGMENTS` on a 16 GB job.
- The fit holds on two processes. The base covers the pool, measured over the whole cgroup, so the cap is taken before the pool starts.
- A circuit over the cap gets no pack and keeps its somas. Dropping its finer levels to fit is not built.
- One slope for every circuit, set above the rate with no sharing. It cannot see sharing: a circuit that shares its morphologies far more than CA1 holds less than the cap allows for. A cap counting placed and distinct segments apart would help only with `MAX_SEGMENTS` raised too; not built.
