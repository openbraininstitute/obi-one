# Circuit Customization — Development Spec

## Overview

Allow users to create **customized circuits** by uploading modified components (edges, e-models, mechanisms, nodes, node sets) as overrides to an existing parent circuit. The system creates a new circuit entity, stages the merged result, validates it asynchronously, and transitions its lifecycle status accordingly.

## Architecture

```
User uploads overrides
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  POST /declared/circuit/customize  (obi-one API)        │
│                                                         │
│  1. Fetch parent circuit from entitycore                │
│  2. Layer 1 sync validations:                           │
│     • Edge HDF5 structure + no NaN/Inf                  │
│     • HOC begintemplate/endtemplate                      │
│     • MOD NEURON block presence                         │
│     • Node HDF5 structure                               │
│     • Node sets JSON validity                           │
│     • HOC↔MOD cross-check (mechanisms referenced exist) │
│     • Nodes↔HOC consistency                             │
│     • New MOD must not be synapse (no NET_RECEIVE)      │
│  3. Stage parent (symlinks) + overlay overrides         │
│  4. Compute metadata (get_circuit_size, properties)     │
│  5. Upload merged directory as sonata_circuit asset     │
│  6. Generate sync assets (node_stats, network_stats,    │
│     circuit_visualization, simulation_designer_image)   │
│  7. Create Circuit entity (lifecycle_status=draft)      │
│  8. Create derivation link (circuit_customization)      │
│  9. Submit validation job to launch-system              │
│                                                         │
│  Returns: { circuit_id, status: "draft" }               │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Validation Task  (runs in Docker container via         │
│  launch-system orchestrator)                            │
│                                                         │
│  Image: obi-one (pre-built with NEURON, bluecellulab,  │
│         bluepysnap, entitysdk)                          │
│  Entry: launch_scripts/launch_circuit_validation/main.py│
│                                                         │
│  1. Stage merged circuit from entitycore (EFS/S3)       │
│  2. Compile MOD files with nrnivmodl (if present)       │
│  3. Validate HOC loading with bluecellulab              │
│  4. Validate morphology/emodel paths exist              │
│  5. Run bluepysnap circuit_validation.validate()        │
│  6. Subset checks against parent (if customization):    │
│     • New populations must not be biophysical           │
│     • Content subset of parent (morphologies, emodels)  │
│  7. Update lifecycle_status:                            │
│     • 0 fatal errors → active                          │
│     • ≥1 fatal errors → disqualified                   │
│                                                         │
│  On success: launch-system fires callback →             │
│  POST /declared/circuit/{id}/generate-assets            │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Asset Generation Task (async, re-launchable)           │
│                                                         │
│  Generates:                                             │
│  • compressed_sonata_circuit                            │
│  • circuit_connectivity_matrices                        │
│  Does NOT affect lifecycle_status                       │
└─────────────────────────────────────────────────────────┘
```

## Simulation Gate

The simulation launch endpoint checks `lifecycle_status == active` before allowing a circuit to be simulated. Circuits in `draft` or `disqualified` state are rejected with a clear error.

## API Endpoint

```
POST /declared/circuit/customize
Content-Type: multipart/form-data

Form fields:
  parent_circuit_id: UUID (required)
  name: str (required)
  description: str (optional)
  emodel_population_manifest: str (optional, JSON mapping filename → population)

File fields (at least one required):
  edges_files: list[UploadFile]       — Edge population H5 files
  emodel_files: list[UploadFile]      — HOC e-model files
  mechanism_files: list[UploadFile]   — MOD mechanism files
  node_files: list[UploadFile]        — Node population H5 files
  node_sets_file: UploadFile          — SONATA nodeset JSON
  circuit_config_file: UploadFile     — circuit_config.json override
```

## Lifecycle Status Values

| Status | Meaning |
|--------|---------|
| `draft` | Entity created, validation pending or in progress |
| `active` | Validation passed, circuit is simulatable |
| `disqualified` | Validation failed (errors stored in task logs) |

Note: entitysdk v0.18.0 only has `draft` and `active`. The `disqualified` value exists in entitycore but needs to be added to the SDK.

## Validation Details

### Layer 1 (Sync, at upload time)
Fast checks that reject immediately with HTTP 422:
- Edge files: valid HDF5, `edges` group, required columns, no NaN/Inf in floats
- HOC files: `.hoc` extension, `begintemplate`/`endtemplate` structure
- MOD files: `.mod` extension, `NEURON` block present
- Node files: valid HDF5, `nodes` group
- Node sets: valid JSON, SONATA expression syntax
- Cross-checks: HOC mechanisms available (built-in + provided MODs + parent), unused HOC detected, new MODs must not have `NET_RECEIVE`

### Layer 2 (Async, in validation task)
Full circuit validation after merge:
- `nrnivmodl` compilation of MOD files
- `bluecellulab.Cell` instantiation per HOC template
- `bluepysnap.circuit_validation.validate()` structural checks
- Morphology/emodel path existence (respects `alternate_morphologies` H5 format)
- Parent subset checks for customizations
- Relative paths resolved against circuit_config.json directory

## Key Files

| File | Purpose |
|------|---------|
| `app/endpoints/circuit_customization.py` | Upload endpoint, Layer 1 validation, staging, job submission |
| `app/endpoints/circuit_registration.py` | Registration endpoint (parallel flow), generate-assets trigger |
| `obi_one/scientific/tasks/circuit_validation/task.py` | Async validation logic (Layer 2) |
| `obi_one/scientific/validations/emodels.py` | Shared HOC/MOD validation functions |
| `obi_one/utils/circuit_customization/staging.py` | Merge parent + overrides into staged directory |
| `launch_scripts/launch_circuit_validation/main.py` | Entry point for the validation Docker job |
| `launch_scripts/launch_circuit_validation/dependencies/default.txt` | ``obi-one`` (pip-installed on neurodamus image) |
| `tests/integration/test_circuit_customization.py` | Integration tests |

## Executor Configuration

### Production (ECS)
- Image: launch-system ``python_3_12_openmpi5_neuron9_neurodamus``; deps from ``dependencies/default.txt`` (``obi-one``)
- Job spec: `image_type: python_3_12_openmpi5_neuron9_neurodamus`, `ref: tag:<APP_VERSION>`
- Auth: `PERSISTENT_TOKEN_ID` via auth-manager

### Local Testing
- Same neurodamus image type when submitting through launch-system; for fully local runs, use a venv with ``obi-one`` installed
- Auth: reads `ENTITYCORE_ACCESS_TOKEN` when set (see launch script)

## Integration Tests

| Test | What it proves |
|------|----------------|
| `test_register_returns_draft` | Sync registration creates entity with `lifecycle_status=draft` |
| `test_assets_generated` | Sync assets (node_stats, network_stats, visualization) produced |
| `test_validation_completes` | Async validation transitions draft → active |
| `test_async_asset_generation` | generate-assets endpoint accepts request for active circuit |
| `test_alzheimer_customization` | Full customization bundle: modified HOC + edges + nodes → async validation completes |
| `test_bad_hoc_rejected` | Layer 1 sync rejection for malformed HOC |
| `test_new_synapse_mod_rejected` | Layer 1 sync rejection for new synapse MOD |
| `test_customized_circuit_has_derivation` | Derivation link (root_circuit_id) correctly set |
| `test_draft_circuit_rejected` | Simulation gate rejects non-active circuits |
| `test_valid_mod_accepted` | MOD+HOC customization passes sync validation |
| `test_mod_compilation_fails` | (xfail) Broken MOD passes Layer 1, fails async compilation |

## Known Limitations / Follow-ups

1. **entitysdk `disqualified`**: Not yet in the published package (v0.18.0). Needs a release. Currently patched in the local Docker image.
2. **Callback mechanism**: The local executor doesn't fire `job_on_success` callbacks. The `test_async_asset_generation` simulates this by calling the endpoint directly.
3. **Single container name**: The local executor reuses container name `obi_one` — only one validation job can run at a time. Production (ECS) doesn't have this limitation.
4. **Test circuit data**: The tiny N=10 test circuit has datatype warnings (float64 vs float32, int16 vs uint) from bluepysnap. These are tolerated as warnings, not fatal errors.
5. **Morphology SWC files**: The test circuit uses H5 morphologies (`alternate_morphologies.h5v1`) — individual SWC files are referenced in node properties but not physically present. This is expected for the compact test archive.
