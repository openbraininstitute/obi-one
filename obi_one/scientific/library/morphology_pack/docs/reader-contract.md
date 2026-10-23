# What the browser's reader relies on

The circuit viewer reads packs in a worker of its own, in TypeScript. [format.md](format.md) is the specification it is written from. This page lists what it also relies on, or checks and refuses. A change to the writer that breaks any of it breaks every viewer already deployed, whatever the version says.

## It refuses

| A pack that | Why |
| --- | --- |
| Does not start with `MPCK` | Not a pack |
| Has a version other than 1 | The format changed in a way it would misread |
| Has a `layout` other than `"space"` | Only packs cut in chunks of space are read |
| Has an index missing a field it requires, or of the wrong kind | A malformed index |
| Has levels whose chunks use more than one `chunkSteps` | Boxes are the same at every level |
| Has a level whose `box`, `bytes`, `segments` and `reach` disagree in length, or whose chunks' segments do not sum to the level's | The index at odds with itself |
| Has a level whose `base` is not a later level in the index | A level's base is coarser and comes after it |
| Has two chunks of one level in the same box | A box has at most one chunk a level |
| Has a somas block that is not 16 bytes a cell | Its cells are the populations' |
| Has a chunk whose counts are not the base's segments in that box, or more segments than the index says | A chunk at odds with its base |
| Differs from its asset's size or SHA-256 digest | A download cut short or damaged |

## It relies on

- **The order on disk.** The somas come right after the index, then every level coarsest first, and each level's chunks in the index's order.
  - A box is readable at a level once the bytes of its chunk there, and of its bases' chunks, are in.
  - The viewer streams the file and draws each box as soon as it can. Written in another order, a pack still reads, but shows nothing past the somas until the file is in.
- **Boxes numbered from the middle out.** In a streamed level, the boxes near the middle of the circuit come first.
- **`reach`.** The viewer grows each box's cube by the farthest reach of its chunks at any level, and culls by that. A segment lying further outside its cube than its chunk's reach says can be culled while it is in view.
- **The populations' `boxes`.** The viewer frames the cells it shows by the boxes of their populations and of the section types it draws. It uses them only where every population has them, else the whole pack's `bounds`.
- **Cells numbered through the populations in the index's order,** sorted by name. The viewer matches them to the circuit's node populations by name.
- **Unknown fields of the index are ignored.** The index's schema strips what it does not name. A new field must therefore be one a reader may do without, as [Growing the format](format.md#growing-the-format) asks.
- **Somas of radius zero** are cells without a morphology, and a soma without a finite position is a cell not placed.
- **Inflating through the browser's own `DecompressionStream('deflate')`.** Every block must be a standard zlib stream. Ending deflate blocks with `Z_BLOCK`, or deflating with `Z_FILTERED`, keeps it so. A coder other than deflate needs a decoder shipped to the browser.
- **The base's boxes, kept as whole numbers.** Up to 64 MiB of them are kept while the finer levels are read over them. A level read over its base needs the base's segments in the same order the writer followed them.

## How it fetches and keeps a pack

- The pack is the circuit's `circuit_morphology_pack` asset. It is fetched whole, by the asset's download URL, in one request; a download cut short resumes once with a range request from where it stopped.
- **The cache:** a pack is kept a month in the browser's Cache Storage, in a bucket of its own, keyed by the download URL. A pack never changes under its asset, so a rebuilt pack is a new asset, and is fetched again.
- **No range reads:** a box is read from the file as it streams in, not fetched by its own byte range.

## What it does not get

- **Section ids.** A single-neuron circuit stays on its per-cell path, which reads its morphology for location picks and synapses. A pack is not built for it.
- **Traced points.** The finest level is simplified within 0.125 µm, and the viewer shows what the pack holds.
