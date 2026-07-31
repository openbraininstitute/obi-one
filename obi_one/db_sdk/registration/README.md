# Entity registration

Reusable code for registering major entities into entitycore via `entitysdk`.

One subfolder per entity type. Each exposes its public API through its `__init__.py`, so
callers import `from obi_one.db_sdk.registration.<entity> import ...` and never reach into
the inner modules.

```
registration/
├── circuit/            assets.py, generate.py, links.py, register.py, resolve.py
├── morphology/         register.py
└── simulation_result/  register.py
```

## What belongs here

Registration logic shaped by the *entity*, reusable across callers: building the
entitysdk model, uploading its assets, wiring up its `Contribution` / `Derivation` /
publication links.

## What does not

- **Task-side `_register_output` methods.** These assemble a name and description from task
  config and then delegate here. They stay with their task — e.g.
  `tasks/circuit_extraction/task.py` and `tasks/synapse_parameterization/task.py`.
- **FastAPI endpoints that register.** The registration there is thin and entangled with
  request handling. Leave it in `app/endpoints/`.
- **Compute helpers.** Meshing, morphometrics, SONATA manipulation and the like stay in
  `scientific/library/` and `utils/`. Importing them from here is fine and already done —
  `circuit/generate.py` imports `obi_one.utils.circuit`, and `morphology/register.py`
  imports `scientific/library/morphology_mesh.py`.
- **Staging and read helpers.** `db_sdk.resolve_circuit` fetches and stages a circuit for
  reading rather than registering one, so it stays in `db_sdk.py` despite being
  circuit-specific.

## Candidates not yet moved

Assessed 2026-07-30. Ranked by how cleanly they would drop in.

### 1. `tasks/skeletonization/registration.py` → `registration/morphology/`

154 lines, entirely registration: a `DigitalReconstructionCellMorphologyProtocol`, then a
`CellMorphology`, then `Contribution` and `Derivation`.

Worth noting the sequencing: lines 139 and 146 construct `models.Contribution` and
`models.Derivation` directly, duplicating what `circuit/links.py` already does in
`register_contributions` and `register_derivation`. Those two are not circuit-specific
despite where they live. Hoisting them to a shared `registration/links.py` is probably the
better first step, and may leave little enough behind that this file can just stay put and
call into `registration/morphology/`.

### 2. `tasks/ion_channel_modeling.py` — extract, don't move

The largest remaining registration surface: roughly 180 of 620 lines across
`create_campaign_entity_with_config` (:222), `create_campaign_generation_entity` (:254),
`create_single_entity_with_config` (:275), `register_json` (:353), `register_thumbnail`
(:365), `register_plots` (:384), `register_plots_and_json` (:396) and `save` (:420),
registering `IonChannelModelingCampaign`, `IonChannelModelingConfig`, `IonChannelModel`,
`UseIon` and `NeuronBlock`.

These are methods on `IonChannelFittingTask`, interleaved with fitting compute. Untangling
them is a real refactor, not a file move.

### 3. `tasks/create_recording_array/create_recording_array.py` — extract, don't move

About 48 lines registering `SimulatableExtracellularRecordingArray` plus three assets
(`register_entity` at :257, uploads at :260/:276/:285), inline in `execute()` and mixed with
BlueRecording weight computation.

### 4. GLB mesh upload — deduplicate first

`library/morphology_mesh.py:47` and `app/endpoints/convert_morphology_to_registered_mesh.py:108`
are both called `mesh_and_upload` and both upload an `AssetLabel.cell_surface_mesh` GLB.
The endpoint also has `_upload_glb_asset` at :71. Resolve the duplication before deciding
what, if anything, moves — the upload half would belong in `registration/morphology/assets.py`.

### Deliberately left alone

- `tasks/em_synapse_mapping/register.py` (78 lines) — already a thin adapter over
  `circuit.register_circuit`; moving it buys nothing.
- `app/endpoints/publication.py`, `contributor.py`, `mesh_registration.py`,
  `morphology_metrics_calculation.py` — registration entangled with request handling.

## Gotchas

**Patch where the name is bound, not where it is defined.** `circuit/generate.py` imports
the asset helpers from `circuit/assets.py` at module level, so tests must patch
`...registration.circuit.generate.add_image_assets`. Patching the `assets` module misses the
already-bound name and lets the real uploader run.

**`app/services/validator.py` hardcodes the write API.** Its `_WriteInterceptingClient`
intercepts exactly `register_entity`, `upload_file` and `update_entity`, and asserts on call
counts. Any refactor changing which client methods get called will silently break config
validation without failing here first.

**libsonata always gives report files an `.h5` suffix.** `simulation_result/register.py`
resolves each voltage report's content type from its extension, which is only safe because
`SimulationConfig.report(name).file_name` appends `.h5` when the configured name lacks it —
verified: `weird.dat` comes back as `weird.dat.h5`. That is why `simulate_brian2.sonata_main`
could drop its hardcoded `application_x_hdf5` without any behaviour change.

**SimulationResult name and description are parameterized but unused.** Both backends take
the defaults, `"Simulation result"` / `"Simulation result"`. Before the two implementations
merged, neuron registered `"simulation_result"` / `"Simulation result"` and brian2
registered `"Simulation result"` / `""`. The arguments remain available for future
backends — just keep existing callers on the defaults.
