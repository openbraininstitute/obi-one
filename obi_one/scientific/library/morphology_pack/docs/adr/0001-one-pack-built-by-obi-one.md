# 0001. Morphologies reach the viewer as one binary pack built by OBI-One

- Status: Accepted in part. The endpoint that built the pack on request is superseded by [0015](0015-built-in-the-asset-job.md), and the ceiling of 212M traced points by [0017](0017-memory-cap.md).
- Date: 2026-10-13

## Context

The circuit viewer drew a large circuit as somas only. Its morphologies were to be drawn in the browser, for circuits of thousands of cells and up to the whole FlyWire brain. The viewer could already load a few hundred cells by itself, a file a cell, at about 12 files a second. More cells, and a fast first view of any circuit, needed the morphologies in a form the browser reads without parsing.

## Decision

A circuit's morphologies reach the viewer as one binary file, the pack, written by OBI-One from the circuit's SONATA files: every biophysical cell's morphology, simplified, placed in the circuit and cut into chunks of space. The browser reads it and cuts nothing.

As first decided, an endpoint built the pack while the viewer waited, up to 5,000 neurons, 256 MiB of files and 5M points, until packs were stored on circuits. A circuit over 212M traced points, FlyWire's size, was to get no pack.

## Alternatives weighed

The first review's figures: every point, deflate 9, on the 1,379-cell fly sample (25 nm grid) and 291 rat cells (36 nm, their data's own step), headless Chrome and OBI-One's Python on one core of the M4 Pro, 2026-10-13.

| Option | What it gave against the pack | Verdict |
| --- | --- | --- |
| Per-cell JSON from the existing endpoint | A request a cell, refused above small scale. A cell of a circuit whose morphologies are one container downloads the whole container. | Kept for single-neuron circuits only ([0018](0018-no-pack-for-single-neurons.md)) |
| SWC or HDF5 as stored | The fly sample: 90.9 MB of SWC against 6.2 MB packed. The rat cells: 43.9 MB of HDF5 against 8.1 MB. About 3 bytes a point packed, 15 times less than SWC text. The same fly cells parse from SWC in 0.6 to 0.7 s, against 68 to 75 ms to read the pack. | Rejected |
| The browser building from files | FlyWire's 1 µm level cut in the browser from its finest level takes 42 s of a thread; the finer levels 4.0 min and some 3.7 GB held at once. FlyWire's files are 9.1 GB of SWC. | Rejected |

## Consequences

- OBI-One needs nothing new to write a pack: MorphIO, libsonata, numpy and zlib. The fly sample packs in 1.2 s of one core; the whole fly brain's 212M points in about 2 core-minutes, besides reading the files.
- The browser needs nothing new to read one: its own `DecompressionStream` inflates, and every number sits where the index says.
- The pack is a derived file. It is rebuilt when its format or the circuit changes.
- The endpoint held a build in the service's own process, one at a time. It was replaced by a step in the circuit asset job ([0015](0015-built-in-the-asset-job.md)).
- The ceiling counted traced points before simplification. It was replaced by a cap on the segments of every level together, taken from the build's memory ([0017](0017-memory-cap.md)).
