# Circuit morphology pack

A pack holds the morphologies of a circuit's biophysical neurons in one binary file, ready for a viewer to draw: simplified, placed in the circuit and cut into chunks of space. It is written by `obi_one.scientific.library.morphology_pack`, whose `circuit` module takes a SONATA circuit's populations to a pack, and served by `GET /circuit/viz/{circuit_id}/morphology-pack`.

## The endpoint

`GET /circuit/viz/{circuit_id}/morphology-pack?max_segments=2000000` answers with the pack as `application/octet-stream`.

The endpoint is temporary. Circuit registration is to build the pack and store it on the circuit, and the circuits already registered are to get theirs in a backfill. The endpoint is removed once both are done, because it builds the pack while the viewer waits, in the service's own process.

The pack it builds holds one level of detail: the finest that comes to at most `max_segments` segments. The viewer says how many segments it can draw.

It checks a circuit in this order, and refuses as early as it can:

1. The circuit's `number_neurons`, from its entity. Nothing of the circuit is read.
2. The sizes of its node files and morphology files, from the listing of its `sonata_circuit` asset, before each is fetched.
3. The points of its morphologies, counted as they are read.
4. The segments of each level, once the morphologies are simplified.

| Limit | Value | Refusal |
| --- | --- | --- |
| Neurons | 5,000 | `too_many_neurons` |
| Bytes of node and morphology files | 256 MiB | `files_too_large` |
| Points of every cell's morphology | 5,000,000 | `too_many_points` |
| Segments of the coarsest level | `max_segments` | `too_many_segments` |

A refusal is a 422 whose `detail` holds `code`, `reason` and `detail`. A circuit with no biophysical population, or none of whose morphologies can be read, is refused with `no_morphologies`. One pack is built at a time: a request that has waited two minutes for another build gets a 503 with the reason `busy`.

A morphology that cannot be read is left out: a file that is not a morphology, or a name its container does not hold. Its cells are in the pack as somas with a radius of zero. So is a cell whose position or rotation is not a finite number.

Only the node files of the biophysical populations and their morphologies are fetched. A public circuit's files are linked from the mounted store; a private circuit's are downloaded into the request's temporary directory, and deleted as soon as they are read.

## The format

A pack is a header, an index and blocks, back to back. Numbers are little-endian.

| Part | Content |
| --- | --- |
| Header, 12 bytes | `MPCK`, the format's version as uint16 (1), two spare bytes, the index's length in bytes as uint32 |
| Index | JSON, deflated (zlib) |
| Somas | x, y, z and radius of every cell as float32, in micrometres, deflated |
| Chunks | A deflated block for every chunk of every level, in the index's order |

Offsets in the index count from the first byte after the index.

### The index

The index is the `Index` model of `obi_one.scientific.library.morphology_pack.codec`, with its fields spelled in camelCase.

```json
{
  "layout": "space",
  "gridUm": 0.025,
  "radiusSteps": 16,
  "bounds": [[0, -80000, 0], [46000, 1200, 120000]],
  "populations": [{ "name": "S1nonbarrel_neurons", "cells": 10 }],
  "somas": { "offset": 0, "bytes": 123 },
  "levels": [
    {
      "toleranceUm": 0.125,
      "pruneUm": 0.0,
      "chunkSteps": 2000,
      "segments": 151234,
      "runs": 9876,
      "offset": 123,
      "chunks": { "box": [0, -3, 5, 0, -3, 6], "bytes": [4100, 3900], "segments": [77000, 74234] }
    }
  ]
}
```

- A position is a whole number of steps of `gridUm` micrometres, in the circuit's own frame. `bounds` holds every point of the first level, in steps.
- A radius is `2 ** (step / radiusSteps)` micrometres.
- A cell's number counts through `populations` in their order: the cells of the first population, then those of the second.
- A level drops the end branches shorter than `pruneUm`, then the points within `toleranceUm` of the path and of the diameter.
- A chunk is a cube of `chunkSteps` steps. `box` has three whole numbers a chunk: its corner is `box * chunkSteps`. `bytes` and `segments` have one number a chunk, and a chunk's block starts where the one before it ends, the first at the level's `offset`.

### A chunk

A chunk holds runs. A run is a stretch of segments one after another along one unbranched polyline, all of them ending in the chunk. A segment belongs to the chunk its far point lies in, so a run's first point may lie outside its chunk. Nothing is cut at a chunk's wall.

A chunk's block, inflated, starts with the number of runs and the number of segments as two uint32. Eleven streams of whole numbers follow.

| Stream | A number for each | Signed |
| --- | --- | --- |
| Cell, as the difference from the run before | run | no |
| Section type, as in SWC: 2 axon, 3 basal dendrite, 4 apical dendrite | run | no |
| Length in segments | run | no |
| First point: x, y, z against the chunk's corner, then the radius step | run, four streams | yes |
| Far point: x, y, z and radius step, each against the segment's near point | segment, four streams | yes |

A stream is one byte giving the width of its numbers in bytes, 1 to 4, then every number's lowest byte, then every number's next byte, and so on. A signed number is stored zigzag: `(n << 1) ^ (n >> 31)`.

Runs are ordered by cell within a chunk. A segment's near point is the far point of the segment before it in its run, or the run's first point.

### What is in it

- A neurite that leaves the soma starts with a segment from the soma's centre, as wide at both ends as the neurite's first traced point.
- A soma is one sphere of NeuroM's soma radius: that of a single point, the mean distance of a contour's points from their centre, or the radius of the sphere with the area of a stack of cylinders.
- Simplification is Ramer-Douglas-Peucker on x, y, z and twice the radius, section by section. It is the morphology viewer's measure, so a pack's finest level is what that viewer draws at the same tolerance.
- The far level joins the sections that pruning leaves end to end before it is simplified.
