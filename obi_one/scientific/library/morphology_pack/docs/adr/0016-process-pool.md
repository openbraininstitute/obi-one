# 0016. Simplification and encoding over a process pool of at most 8; the same bytes on any number

- Status: Accepted
- Date: 2026-10-19

## Context

Two stages of a build take most of its time and split into independent pieces: simplifying each distinct morphology, and encoding each chunk. On CA1's first 1,500 cells, on two processes, simplifying took 4.7 s of 10.3 and packing 3.3 s (M4 Pro, 2026-10-23). The job's machine has 1 to 4 cores. A pack is stored and compared, so it must not depend on the machine it was built on.

## Decision

- Both stages run over `Processes`, a pool forked from a server that has the pack's modules imported. Morphologies go `MORPHOLOGIES_A_JOB` = 4 a job, chunks `CHUNKS_A_JOB` = 8.
- The processes are one a CPU the build may use, within its container's quota, v2 or v1, and at most `MAX_WORKERS` = 8, unless the caller gives a number.
- Results come back in the order of the work, so the pack is the same to the byte on any number of processes.
- Each process hands its freed memory back after each job, and results are unpickled in the caller's thread, where the main process's freed memory can be reused.

## Alternatives weighed

| Option | What it gave against the pool | Verdict |
| --- | --- | --- |
| One process | The packing of five copies of the 1,379-cell fly sample: 3.8 s on one process, 1.6 s on eight (M4 Pro, 2026-10-19) | Kept as the fallback: `workers=1`, no pool |
| More than 8 processes | Past about eight, the main process's own work, chunk by chunk, keeps the others waiting, while each holds its own memory: about 110 MB more each past two while simplifying. A container with no CPU limit would start one for every CPU of its node | Rejected |

## Consequences

- What makes the bytes the same, and what a change must keep:
  - a chunk's block depends on its own segments alone;
  - chunks are numbered by distance with ties broken by place ([0012](0012-order-on-disk-and-one-download.md));
  - a point is turned and moved by sums of products, not a matrix product, which rounds a row by where it sits ([0003](0003-grid-and-radius-steps.md)).
- The tests build the same pack alone and on two processes, in the writer and in the whole build. CA1 and five copies of the fly sample were checked the same to the byte on 1 and 4, and 1 and 8, processes.
- The cap reserves `BYTES_A_WORKER` = 128 MiB for each process past two ([0017](0017-memory-cap.md)).
- A script that uses the pool keeps its work under `if __name__ == "__main__"`: each process imports the main module.
