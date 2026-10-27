# Circuit morphology pack in OBI-One

A pack holds the morphologies of a circuit's biophysical neurons in one binary file, ready for a viewer to draw: simplified, placed in the circuit and cut into chunks of space. It is written by `obi_one.scientific.library.morphology_pack`, and stored on the circuit as its `circuit_morphology_pack` asset, `circuit.mpack`, as `application/octet-stream`.

This page is how OBI-One builds and stores packs. The pack itself is documented beside its code, in [`obi_one/scientific/library/morphology_pack/docs/`](../../obi_one/scientific/library/morphology_pack/docs/README.md):

- [the format](../../obi_one/scientific/library/morphology_pack/docs/format.md);
- [what the browser's reader relies on](../../obi_one/scientific/library/morphology_pack/docs/reader-contract.md);
- [how a pack is built](../../obi_one/scientific/library/morphology_pack/docs/architecture.md);
- [the decisions](../../obi_one/scientific/library/morphology_pack/docs/adr/README.md);
- [the alternatives weighed](../../obi_one/scientific/library/morphology_pack/docs/alternatives.md);
- [the measurements](../../obi_one/scientific/library/morphology_pack/docs/performance.md).

## Where a pack is built

A pack is one of a circuit's assets, built with the others by `generate_additional_circuit_assets`, last, so that the others are in when a job's time runs out while it builds.
- It is built when the circuit has none, or with `force`. One still uploading counts as none.
- It holds every level.
- A single-neuron circuit gets none: the viewer draws it from its morphology.

It is built in three places:

- **The circuit asset job.** Registration and customization launch it once the circuit is validated, and `POST /declared/circuit/{circuit_id}/generate-assets` launches it again.
  - The endpoint launches nothing when the circuit has all of its compressed circuit, its connectivity matrices and, past single scale, its pack.
  - Where the pack is the only asset missing, the job fetches only what the pack needs: the circuit's config, the node sets, the nodes, and the biophysical populations' morphologies.
- **The task that registers the circuit,** where its machine is enough.
  - Synapse parameterization, launched for at most 20 neurons, builds it there.
  - Building a synaptome and EM synapse mapping make single-neuron circuits, so no pack.
- **Circuit extraction's callback.** Extraction registers its circuit on a machine sized for the extraction, so its task definition's `after_success` hook, `build_missing_circuit_assets` in `app/endpoints/circuit_helpers.py`, runs on the job's success through `POST /declared/task/callback/after-success`. It has the asset job build the assets missing from each circuit the task's activity generated, those `generate-assets` checks for.

The job reads a circuit's files in this order:
1. through the client's local store, where it holds them;
2. from the public data mounted on the job's Fargate executors;
3. by download, for the rest.

`morphology_pack.staging.stage_morphology_pack_inputs` does the fetching. It stays in OBI-One when the pack package leaves it.

## The job's machine

The machine follows the circuit's scale, `ASSET_GENERATION_RESOURCES` in `obi_one/db_sdk/registration/circuit/launch_jobs.py`. Every job has an hour.

| Scale | Cores | Memory |
| --- | --- | --- |
| single, pair, small | 1 | 4 GB |
| microcircuit | 2 | 16 GB |
| region, system, whole brain | 4 | 16 GB |

- **Why 16 GB is enough:** it holds a pack of `MAX_SEGMENTS` (300M segments, above the whole FlyWire brain's) on either two or four processes.
- **Scale from registration:** registration computes the scale from the neuron count, up to microcircuit. A larger circuit gets the 4 cores only where it was registered with a larger `scale_override`.

The build runs over one process a CPU the container allows, at most eight. The pack is the same to the byte on any number of processes.

## When a circuit gets no pack

Each case is logged. The circuit's viewer then shows its somas.

| Why | Log line |
| --- | --- |
| No biophysical population | `No morphology pack for circuit <id>: The circuit has no biophysical population` |
| None of its morphologies can be read | `No morphology pack for circuit <id>: None of the circuit's morphologies could be read` |
| Its levels come to more segments than the build may hold here | `No morphology pack for circuit <id>: The circuit's levels come to over the <n> segments a pack may hold here` |
| A single-neuron circuit | `Circuit <id> is a single neuron — skipping circuit_morphology_pack` |
| A pack already there, without `force` | `circuit_morphology_pack already present on circuit <id> — skipping` |

The segments a build may hold are the lesser of two limits:
- `MAX_SEGMENTS`, whatever the machine;
- what the container's memory leaves the build, as the package's README gives it.

The log says which of the two decided, before the build starts:
- `Morphology pack capped at <n> segments by <bytes> bytes of memory left`, where the memory decided;
- `Morphology pack capped at <n> segments`, where `MAX_SEGMENTS` did.

Some cells get only a soma, with a radius of zero. Each case logs a warning, and the pack is built with the rest:

| Why | Warning |
| --- | --- |
| A morphology that cannot be read: a file that is not a morphology, or a name its container does not hold | `Morphology <name> left out: it could not be read` |
| No finite position or rotation | `<n> cells of population <name> are somas alone: no finite position or rotation` |

Each stage of a build logs its time as it ends: `Morphology pack: <n> morphologies read in <s> s`, then the levels simplified, the cells placed and the bytes packed.

## Who may write the pack

entitycore lets only members of a circuit's project add an asset to it, whether the circuit is public or not. OBI-One acts with the caller's token, so:

- a pack is built where the circuit's owner's job runs, at registration or by `generate-assets`;
- a viewer from another project cannot start a build for a public circuit;
- removing an asset from a public circuit takes a service maintainer.

A circuit registered before packs were built gets one when `generate-assets` is called for it by a member of its project.
