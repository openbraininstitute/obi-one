# Christoph review follow-ups — change log

Review companion for PR [#844](https://github.com/openbraininstitute/obi-one/pull/844) (circuit customization / registration).
Use this to walk the 11 addressed items one by one.

**Deferred (not in this list):** fine-grained post-validation callbacks.

---

## 1. Prefer SNAP for emodel paths, model templates, population sizes, `mechanisms_dir`

**Review ask:** Stop manual JSON / h5py parsing; use SNAP so global vs per-population components resolve the same way.

**What changed** (`obi_one/scientific/tasks/circuit_validation/task.py`):

| Helper | Before | After |
|---|---|---|
| `_validate_emodel_paths` | libsonata `expanded_json` + manual dirs | SNAP `pop.config["biophysical_neuron_models_dir"]` + `model_template` |
| `_read_model_templates` | h5py over nodes file | **Removed** (SNAP properties) |
| `_get_population_sizes` | h5py node counts | SNAP `pop.size` |
| `_collect_hoc_files` | JSON component dirs | SNAP per-population `biophysical_neuron_models_dir` |
| `_find_mod_dir` | JSON `components.mechanisms_dir` | SNAP `pop.config["mechanisms_dir"]` |
| `_compute_population_dynamics` | `_get_pop_config` JSON | `pop.config` only |

**Tests:** `tests/obi_one/scientific/tasks/circuit_validation/test_task.py`, `test_task_helpers.py`

**How to review:** Open each helper above and confirm no leftover libsonata/h5py for those concerns. Remaining JSON/h5py is intentional (id_mapping read, dynamics write, subset checks that still need raw config in places).

---

## 2. Use `TYPES_OF_VIRTUAL_NODES` / `TYPES_OF_POINT_NODES`

**Review ask:** Don’t hard-code `{"virtual", "point_neuron"}`; reuse constants from `circuit_metrics.py`.

**What changed:**

- Import `TYPES_OF_BIOPHYS_NODES`, `TYPES_OF_VIRTUAL_NODES`, `TYPES_OF_POINT_NODES`
- `_ALLOWED_NEW_POPULATION_TYPES = virtual ∪ point`
- Morph / emodel / HOC collect / dynamics only run for `TYPES_OF_BIOPHYS_NODES` (not “skip virtual only”)
- `_check_new_populations_not_biophysical` uses SNAP + the shared type sets

**How to review:** Grep `task.py` for `"virtual"` / `"point_neuron"` string literals — remaining uses should be in messages or type maps, not ad-hoc allowlists.

---

## 3. Point-neuron type must match `target_simulator`

**Review ask:** e.g. do not allow `brian2_point` on a NEURON circuit.

**What changed:**

```text
brian2_point              → Brian2
inait_point_neuron_lif    → LearningEngine
point_neuron / point_process → NEURON, CORENEURON
```

- `_point_type_matches_simulator` + wiring through `_check_new_populations_not_biophysical(..., target_simulator=circuit.target_simulator)`
- New populations that are point types are checked when customization subset checks run

**Tests:** `TestCheckNewPopulationsNotBiophysical` (allow/reject cases for Brian2 / LearningEngine / NEURON)

**How to review:** Confirm mapping matches product intent (especially CORENEURON with `point_neuron`).

---

## 4. ID-mapping: remove whenever stale (not only if symlink)

**Review ask:** Symlink-only removal is confusing; stale `id_mapping.json` should be removed in any case.

**What changed** (`_validate_id_mapping_files`):

- On stale mapping: always `unlink()`, single warning message
- Docstring updated; no symlink branch

**Tests:** `test_stale_mapping_removed` (was `test_stale_mapping_non_symlink`)

**How to review:** Note this operates on the **staged** circuit copy during validation. Confirm that is enough for your asset lifecycle, or if the entity asset must be updated too.

---

## 5. Launch `is_customization` via derivation type

**Review ask:** `root_circuit_id is not None` is wrong; use derivation type `circuit_customization`.

**What changed:**

- `is_circuit_customization(circuit)` / `customization_parent_entity(circuit)` in `task.py`
- `launch_scripts/launch_circuit_validation/main.py` uses `is_circuit_customization(circuit)`
- Subset checks parent lookup only follows a `circuit_customization` derivation’s `used` entity

**Tests:** `TestCircuitCustomizationHelpers`; subset-check mocks set `derivation_type=DerivationType.circuit_customization`

**How to review:** Registration-with-parent (non-customization derivation) should **not** set `is_customization=True`.

---

## 6. Optional draft-only validation + overwrite flag

**Review ask:** Skip validation unless circuit is `draft`; allow overwrite when manually re-triggered.

**What changed** (`launch_scripts/launch_circuit_validation/main.py`):

- `--force` (`true`/`false`, same pattern as asset generation)
- If not force and `lifecycle_status != draft` → log + exit 0 (skip)
- Automatic post-register/customize path leaves circuits in `draft`, so they still validate

**How to review:** `trigger_validation_task(..., force=...)` forwards `--force`;
`POST /declared/circuit/{id}/validate?force=true` re-validates non-draft circuits.

---

## 7. Nodeset validation fixes

**Review ask:**

- `node_id` must be a list (no single int)
- Allow `bool` attribute filters
- Compound node sets = list of **strings** only (no nested dicts)

**What changed** (`app/endpoints/circuit_customization.py`):

- `_validate_nodeset_dict` / `_validate_nodeset_list` updated accordingly

**Tests:** `tests/app/endpoints/test_circuit_customization_extra.py` (`TestValidateNodeSetsExtra`)

**How to review:** Compare against [SONATA node sets](https://sonata-extension.readthedocs.io/en/latest/sonata_nodeset.html) if anything still feels too strict/loose.

---

## 8. Parent must be `active` for customize

**Review ask:** Prevent customizing draft / non-active parents.

**What changed** (`customize_circuit_endpoint`):

- After fetch parent: require `EntityLifecycleStatus.active`
- Else HTTP **409** with clear detail

**How to review:** Integration path that registers then customizes must wait until parent validation promotes parent to `active` (existing integration tests already poll lifecycle).

---

## 9. Parent `mechanisms_dir` via SNAP (+ staging new populations)

Treat as two related customization/staging items from the review.

### 9a. Parent mechanisms via SNAP

**What changed** (`_get_parent_mechanism_names`):

- Stage parent → SNAP circuit → union of `*.mod` stems from each pop’s `mechanisms_dir`
- Fallback: `rglob("*.mod")` under staged tree

### 9b. New populations from overridden config

**Review ask:** Staging only replaced existing pops; what about new pops declared in an overridden config?

**What changed** (`obi_one/utils/circuit_customization/staging.py` + endpoint):

1. Apply `circuit_config` override **first**
2. Node/edge overlays use the **active** config
3. With override present, uploads for populations **declared in the override but absent from parent** are copied to the config’s `nodes_file` / `edges_file` path
4. Removed the 422 that forbade combining `circuit_config_file` with `node_files` / `edges_files`

**Tests:** `test_adds_new_population_when_allowed`, `test_new_population_without_config_entry_raises`

**How to review:** New populations still must pass validation rules (virtual/point only + simulator match). Biophysical new pops remain rejected in validation.

---

## 10. Registration: derivation, root vs parent, unused fields, `extract_tar_gz`

**Review asks (bundled):**

- Don’t set `root_circuit_id = parent_circuit_id` (root ≠ parent)
- Create a real derivation when `parent_circuit_id` is set
- Wire unused form fields (`scale_override`, `contact_email`, …)
- Use `obi_one.utils.io.extract_tar_gz` instead of local `_extract_archive`

**What changed** (`app/endpoints/circuit_registration.py`):

| Topic | Behavior now |
|---|---|
| Extract | `extract_tar_gz(...)`; local `_extract_archive` removed |
| Parent | Fetch parent entity; `root_circuit_id = parent.root_circuit_id or parent.id` |
| Derivation | `register_derivation(..., derivation_type=DerivationType(...))` |
| `scale_override` | Overrides computed scale when provided |
| `contact_email` | Passed into `models.Circuit` |
| `license_id` | Resolved to license entity when set |
| `authorized_public` | Passed into `models.Circuit` |

**Still deferred:** none for this item — the HTTP endpoint now calls library
``register_circuit(..., lifecycle_status="draft", skip_validation=True)`` then
triggers the async validation job.

**How to review:** Register with `parent_circuit_id` + `derivation_type` and confirm EntityCore shows derivation + correct root; register without parent and confirm no derivation / no root.

---

## 11. (Index note) Ordering vs original “11”

The numbered list above maps to the work completed in the review pass. Original review also mentioned:

- **App tag once deployed** — done: validation launch uses `tag:{APP_VERSION}` (same as asset generation)
- **Unify on `register_circuit`** — done: HTTP `/circuit/register` delegates to library `register_circuit` with draft + skip_validation
- **Fine-grained success callbacks** — explicitly later

If you want those as items 12–14 in a follow-up doc, say so.

---

## Suggested review order

1. SNAP helpers (#1) — foundation for later checks  
2. Types + simulator (#2–3)  
3. ID mapping + launch customization/draft (#4–6)  
4. Customize endpoint + staging (#7–9)  
5. Registration endpoint (#10)  

## Quick test commands

```bash
make test-file FILE=tests/obi_one/scientific/tasks/circuit_validation/test_task.py
make test-file FILE=tests/obi_one/scientific/tasks/circuit_validation/test_task_helpers.py
make test-file FILE=tests/app/endpoints/test_circuit_customization_extra.py
make test-file FILE=tests/obi_one/utils/circuit_customization/test_staging.py
make test-file FILE=tests/app/endpoints/test_circuit_registration.py
```
