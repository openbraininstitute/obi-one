---
tags:
  - contribute-and-fix-data
---

# Morphology Registration

`POST /declared/register-morphology-with-calculated-metrics` validates an uploaded neuron file
(`.swc`, `.h5`, `.asc`), converts it to the other supported formats, computes morphometrics, and
registers a `CellMorphology` entity with its assets.

## Storing morphologies that fail validation

Some morphologies — raw reconstructions in particular — cannot be parsed or converted. By default
these are rejected outright, so there is no way to store them.

Send `store_if_invalid: true` in the `metadata` form field to register them anyway:

```json
{"name": "Raw cell", "store_if_invalid": true}
```

With the opt-in, a file that fails validation is registered with
`lifecycle_status = disqualified`, and the original upload is kept as an asset. Format
conversion, morphometrics and mesh generation are skipped, because none of them can run on a
file that could not be loaded.

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

The flag only applies when the file itself is not a usable morphology (422). Everything else is
still an error regardless of the flag:

- empty uploads and unsupported file extensions → 400, bad requests rather than bad morphologies
- format conversion failures → 400, since these can be environmental (a full disk, for example)
  rather than a property of the uploaded file

If the entity is registered but the file cannot be attached, the response is a 500 whose detail
includes the `entity_id`, so the upload can be retried or the entity removed.
