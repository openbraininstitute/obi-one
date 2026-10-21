# Circuit morphology pack

A pack holds the morphologies of a circuit's biophysical neurons in one binary file, ready for a viewer to draw: simplified, placed in the circuit and cut into chunks of space. It is written by `obi_one.scientific.library.morphology_pack`, whose `circuit` module takes a SONATA circuit's populations to a pack, and served by `GET /circuit/viz/{circuit_id}/morphology-pack`.

## The endpoint

`GET /circuit/viz/{circuit_id}/morphology-pack?max_segments=2000000` answers with the pack as `application/octet-stream`.

The endpoint is temporary. Circuit registration is to build the pack and store it on the circuit, and the circuits already registered are to get theirs in a backfill. The endpoint is removed once both are done, because it builds the pack while the viewer waits, in the service's own processes.

The pack it builds holds one level of detail: the finest that comes to at most `max_segments` segments. The viewer says how many segments it can draw. With `all_levels=true` the pack holds every level instead, as a pack stored on the circuit is to, and `max_segments` is not used.

It checks a circuit in this order, and refuses as early as it can:

1. The circuit's `number_neurons`, from its entity. Nothing of the circuit is read.
2. The sizes of its node files and morphology files, from the listing of its `sonata_circuit` asset, before each is fetched.
3. The points of its morphologies, counted as they are read.
4. The segments of each level, once the morphologies are simplified.

The limits are settings, so that a service run locally can take larger circuits. Each defaults to the value below.

| Limit | Setting | Default | Refusal |
| --- | --- | --- | --- |
| Neurons | `CIRCUIT_MORPHOLOGY_PACK_MAX_NEURONS` | 5,000 | `too_many_neurons` |
| Bytes of node and morphology files | `CIRCUIT_MORPHOLOGY_PACK_MAX_STAGED_BYTES` | 256 MiB | `files_too_large` |
| Points of every cell's morphology | `CIRCUIT_MORPHOLOGY_PACK_MAX_POINTS` | 5,000,000 | `too_many_points` |
| Segments of the pack, over every level it holds | `CIRCUIT_MORPHOLOGY_PACK_MAX_SEGMENTS` | 5,000,000 | `too_many_segments` |

A pack of one level is also held to `max_segments`, so its coarsest level is refused when it comes to more than the lesser of the two.

A refusal is a 422 whose `detail` holds `code`, `reason` and `detail`. A circuit with no biophysical population, or none of whose morphologies can be read, is refused with `no_morphologies`. One pack is built at a time: a request that has waited two minutes for another build gets a 503 with the reason `busy`.

A morphology that cannot be read is left out: a file that is not a morphology, or a name its container does not hold. Its cells are in the pack as somas with a radius of zero. So is a cell whose position or rotation is not a finite number.

The morphologies are simplified, and the chunks encoded, over `CIRCUIT_MORPHOLOGY_PACK_WORKERS` processes: by default one for each CPU the service may use, within its container's quota, and at most eight, past which the build's own work in the service's process holds them up. They are forked from a server process started with the first build, and the pack is the same to the byte on any number of them.

Only the node files of the biophysical populations and their morphologies are fetched. A public circuit's files are linked from the mounted store; a private circuit's are downloaded into the request's temporary directory, and deleted as soon as they are read.

## The format

A pack is a header, an index and blocks, back to back. Numbers are little-endian.

| Part | Content |
| --- | --- |
| Header, 12 bytes | `MPCK`, the format's version as uint16 (1), two spare bytes, the index's length in bytes as uint32 |
| Index | JSON, deflated (zlib) |
| Somas | x, y, z and radius of every cell as float32, in micrometres, deflated |
| Chunks | A deflated block for every chunk of every level: the levels coarsest first, each level's chunks in the index's order |

Offsets in the index count from the first byte after the index. Laid out coarsest first, a pack streamed in has the somas and every level's bases before the level itself. A reader finds each block by its offset only, so a pack laid out in another order reads alike.

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
      "runs": 0,
      "offset": 12123,
      "base": 1,
      "chunks": {
        "box": [0, -3, 5, 0, -3, 6],
        "bytes": [4100, 3900],
        "segments": [77000, 74234],
        "reach": [12, 0]
      }
    },
    {
      "toleranceUm": 0.25,
      "pruneUm": 0.0,
      "chunkSteps": 2000,
      "segments": 98000,
      "runs": 41,
      "offset": 123,
      "base": null,
      "chunks": { "box": [0, -3, 5, 0, -3, 6], "bytes": [6100, 5900], "segments": [50000, 48000], "reach": [12, 0] }
    }
  ]
}
```

- A position is a whole number of steps of `gridUm` micrometres, in the circuit's own frame. `bounds` holds every point of the first level, in steps.
- A radius is `2 ** (step / radiusSteps)` micrometres.
- A cell's number counts through `populations` in their order: the cells of the first population, then those of the second.
- A level drops the end branches shorter than `pruneUm`, then the points within `toleranceUm` of the path and of the diameter. Levels come finest first.
- `base` is the level this one is read over: the next, coarser one, or `null` for a level read alone, the last.
- A chunk is a cube of `chunkSteps` steps, the same at every level. `box` has three whole numbers a chunk: its corner is `box * chunkSteps`. `bytes`, `segments` and `reach` have one number a chunk, and a chunk's block starts where the one before it ends, the first at the level's `offset`.
- `segments` counts the chunk's segments as read, and `runs` the level's runs, those of its own.
- `reach` is how many steps the chunk's segments lie outside its cube at most, either end and any axis: a reader that culls by chunks grows each cube by it.

### A chunk

A level read over its base holds most of its segments as they follow the base's, and the rest as runs of its own. A segment of the base is followed where the finer level runs from its near point to its far point through points of its own: the inner points. The coarsest level, and any level read alone, holds runs only.

A chunk's segments are, in this order:

1. Those that follow the base's segments in the same box, in the order the base's chunk is read: for each base segment, the segments from its near point through each inner point to its far point, with its cell and type.
2. Its runs. A run is a stretch of segments one after another along one unbranched polyline, all of them ending in the chunk. A segment belongs to the chunk its far point lies in, so a run's first point may lie outside its chunk.

Nothing is cut at a chunk's wall, and a segment that follows a base segment may lie anywhere along it, outside the chunk: `reach` bounds both.

A chunk's block, inflated, starts with four uint32: the base's segments in the box, the inner points, the runs, and the runs' segments. Streams of whole numbers follow.

| Stream | A number for each | Signed |
| --- | --- | --- |
| How many segments follow it: 0, or 1 and more | base segment | no |
| Inner point: x, y, z and radius step, each against the chord's guess | inner point, four streams | yes |
| Cell, as the difference from the run before | run | no |
| Section type, as in SWC: 2 axon, 3 basal dendrite, 4 apical dendrite | run | no |
| Length in segments | run | no |
| How many runs back a run of its cell ends where it starts, or 0 | run | no |
| First point: x, y, z against the chunk's corner, then the radius step | run with 0 just before, four streams | yes |
| First point's radius step against the end of the run it refers to | run with more than 0 just before | yes |
| Far point: x, y, z and radius step, each against the segment's near point, x, y and z less the guess from the step before | segment, four streams | yes |

A stream is one byte giving the width of its numbers in bytes, 1 to 4, then every number's lowest byte, then every number's next byte, and so on. A signed number is stored zigzag: `(n << 1) ^ (n >> 31)`.

- A base segment followed by `k` segments has `k - 1` inner points, in order from its near point. The chord's guess of an inner point is `p + floor((q - p) / left)`, for each of x, y, z and radius step: `p` is the point before it (the base segment's near point, or the inner point before), `q` the base segment's far point, and `left` how many segments are still to come to `q`, the one it ends included.
- A run that refers back starts at the x, y and z of the end of the run it refers to. Its radius step is that end's plus its own number.
- A step's guess, after the first step of a run, is `floor((3 * s + 2) / 4)` of the step before it on x, y and z; the radius step has none.

A block over 1 KB inflated is written as one zlib stream whose deflate blocks end at every byte plane, so each plane gets Huffman tables of its own; any inflater reads it as it reads a block deflated whole.

Runs are ordered by cell within a chunk. A segment's near point is the far point of the segment before it in its run, or the run's first point.

### What is in it

- A neurite that leaves the soma starts with a segment from the soma's centre, as wide at both ends as the neurite's first traced point.
- A soma is one sphere of NeuroM's soma radius: that of a single point, the mean distance of a contour's points from their centre, or the radius of the sphere with the area of a stack of cylinders.
- Simplification is Ramer-Douglas-Peucker on x, y, z and twice the radius, section by section. It is the morphology viewer's measure, so a pack's finest level is what that viewer draws at the same tolerance.
- The far level joins the sections that pruning leaves end to end before it is simplified.
- A finer level follows a base segment wherever its own segments run along the base's path between the same two points: always where both levels prune alike, and over the far level wherever no branch along the way starts apart from its fork, in position or width.
