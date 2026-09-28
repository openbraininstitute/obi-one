---
tags:
  - contribute-and-fix-data
---

# Morphology Registration

`POST /declared/register-morphology-with-calculated-metrics` validates an uploaded neuron file
(`.swc`, `.h5`, `.asc`), converts it to the other supported formats, computes morphometrics, and
registers a `CellMorphology` entity with its assets.

## Storing morphologies that fail validation

Some morphology files cannot be parsed or converted. By default these are rejected outright, so
there is no way to store them.

Send `store_if_invalid: true` in the `metadata` form field to register them anyway:

```json
{"name": "My morphology", "store_if_invalid": true}
```

With the opt-in, a file whose problem is intrinsic to the file itself is registered with
`lifecycle_status = disqualified`, and the original upload is kept as an asset. This covers both
files morphio cannot parse and files that parse but cannot be converted (an unsupported soma
type, for example). Format conversion, morphometrics and mesh generation are then skipped,
because none of them can run on a file that could not be processed.

The flag is a request control only; it is not stored on the entity.

## Response

| Field | Notes |
| --- | --- |
| `lifecycle_status` | `active` when validation passed, `disqualified` when it did not |
| `validation_error` | The reason validation failed; `null` on success |
| `measurement_entity_id` | `null` for disqualified morphologies (no morphometrics) |
| `mesh_asset_id` | `null` for disqualified morphologies, and whenever meshing is unavailable |

Note that with the opt-in a failed morphology returns **200**, not 422. Callers must read
`lifecycle_status` rather than treating any 2xx as a valid morphology.

The flag applies when the failure is a property of the file (a 422): morphio cannot parse it, or
it parses but cannot be converted. Everything else is still an error regardless of the flag:

- empty uploads and unsupported file extensions → 400, bad requests rather than bad morphologies
- system errors during conversion (a full disk, for example) → 500, since these are server
  problems rather than anything wrong with the uploaded file

If the entity is registered but the file cannot be attached, the response is a 500 whose detail
includes the `entity_id`, so the upload can be retried or the entity removed.
