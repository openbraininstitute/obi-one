---
tags:
  - circuit-simulation
---

# Neuronal Manipulation Properties

`POST /circuit-neuronal-manipulation-properties-by-neuron-set` returns the mechanism variables a neuronal manipulation block can change for the neurons of a neuron set: per ion channel, its section lists and, per variable, its units, limits, type (RANGE or GLOBAL) and original value per section list. The UI builds its variable picker from this response.

The variables are read from the hoc and mod files inside the circuit's `sonata_circuit` asset. No `emodel_circuit` derivation is needed, so any circuit with those files works.

## Data flow

1. Stage `circuit_config.json`. With a neuron set, also stage the node sets file and the `nodes.h5` of every population. Without one, only the `model_template` column of each biophysical population is read (see below).
2. Resolve the neuron set to node IDs per population and read their `model_template`. A list in a neuron set field is a scan dimension (`node_set: ["L1_LAC", "L2_IPC"]`): each single-valued copy is resolved and the node IDs are unioned (`get_expanded_neuron_ids`, at most 100 combinations, top-level fields only). `/circuit/{circuit_id}/neuron-set-node-ids` returns the same union.
3. For each template, read `<biophysical_neuron_models_dir>/<name>.hoc`: `insertChannel()` says which mechanism is inserted in which section list, `biophys()` the value of each variable there.
4. List the asset once and fetch every `.mod` file of `<mechanisms_dir>` (or the first of `mod/`, `mechanisms/` that holds one). NEURON names a mechanism by the `SUFFIX` inside the file, not the file name (rCA1 keeps `kdrb` in `kdrbca1.mod`), so the whole directory is indexed by `SUFFIX`. Each mechanism gives its `RANGE` and `GLOBAL` variables and the units declared in `PARAMETER`, `ASSIGNED` or `STATE`. A unit the mod file does not declare is taken from the ion channel model entities with the same `nmodl_suffix` (one search per suffix, in parallel), only when every entity whose shared units match agrees.
5. Keep the channels, variables and section lists common to all templates.

NEURON's built-ins (`pas`, `fastpas`, `hh`, `extracellular`) have no mod file; their variables and units come from a table. `capacitance` and the ion mechanisms add no variable.

## Hoc reader

The hoc files are printed by the BluePyEModel cell template ([format](https://sonata-extension.readthedocs.io/en/latest/hoc-emodel.html)). Inside `insertChannel()` and `biophys()` it prints three line shapes, and only these are accepted:

```text
forsec this.<section_list> { insert <mechanism> }
forsec CellRef.<section_list> { <variable> = <number> }
distribute_distance(CellRef.<section_list>, "<variable>", "<formula>")
```

For `distribute_distance`, the value is the optimised parameter in the formula. Every BluePyEModel distribution is either a product where the value is the only plain number (`exp`, `step`, ...) or the value plus a term linear in the distance (`linear_e_pas_apic`). Any other formula gives `null` and a warning. GLOBAL values come from `check_parameter()`. Any other line rejects the template; nothing is guessed. A test renders a hoc file with the real template and checks the reader returns the input values.

## Fallback and errors

A template falls back to its `emodel_circuit` derivation, with a warning naming the reason, when its hoc file is missing, over 1 MB or not template output, when a mechanism has no mod file (or two), when the asset cannot be listed, or when its population declares no `biophysical_neuron_models_dir`. Warnings quote only the reader's own messages; other errors are given by type, since they can hold signed storage URLs.

Every URL query string (where the signature is) is replaced by `?<redacted>` in the logs. The filter (`obi_one.utils.log_redaction.RedactUrlQueries`) is installed on the root log handler in `app.application`, because the URL reaches the logs from several loggers: httpx2 logs every request URL at INFO, and entitysdk quotes the redirected URL in its errors.

With a neuron set, a circuit without exactly one `sonata_circuit` asset is a 400. Without one, it uses its derivations.

Asset paths built from circuit content are refused when absolute or containing `..`.

## Differences from the derivation path

| Field | Circuit files | Derivation path |
|---|---|---|
| Section lists of a channel | where `insertChannel()` inserts it | where the optimisation output has a parameter |
| Variable names | `RANGE` / `GLOBAL` of the circuit's mod file | `neuron_block` of the ion channel model entity |
| `units` | from the mod file, else from the ion channel model entity | often empty |
| Values not optimised (`cm`, `Ra`, some `vshift*`) | read from `biophys()` | `null` |
| Channel `entity_id` | `null` | ion channel model ID |

The circuit's mod files are the ones the simulation compiles, so the two paths can list different variables.

## Reading `model_template` without a neuron set

A `nodes.h5` can be large (743 MB for nbS1) while its distinct `model_template` values are a few dozen strings. Each biophysical population is read the first way that works:

1. A symlink to the mounted asset store (`FetchFileStrategy.link_only`).
2. Byte ranges. entitycore redirects the download endpoint to a presigned storage URL, and storage serves `Range` requests. `HttpRangeFile` (`obi_one/utils/http_range_file.py`) makes that URL look like a file, given the size from the asset listing (no `HEAD`: S3 refuses it on a presigned `GET` URL). h5py reads the metadata through it in 4 MB blocks. The column itself is read with `read_contiguous_dataset`: a contiguous, uncompressed dataset is one run of bytes, so its offset and size give one exact request sent outside h5py. That matters because h5py holds one process-wide lock around every call, including the file's reads: measured locally, N concurrent reads through h5py took N times as long. `asset_range_file` (`obi_one/db_sdk/assets.py`) builds the file object; it uses two private entitysdk members until entitysdk has a public download-URL method (a `TODO` there; its test uses a real `Client` so a rename fails CI).
3. A full download, when the redirect or the ranges fail (logged) or the size is unknown.

Measured on staging, one run each:

| | nbS1 | rCA1 |
|---|---|---|
| `nodes.h5` size | 743 MB | 59 MB |
| Bytes read | 33.7 MB | 26.8 MB |
| Range requests | 5 | 6 |
| Time to the template set | 6.3 s | 7.2 s |
| Full download before | about 45 s | about 15 s |

With a neuron set the file is still staged whole: bluepysnap and libsonata need a local file.

## Concurrency

File fetches run on `FETCH_POOL`, one 16-thread pool shared by every request in the process, so threads and open connections stay bounded under load. Whole `nodes.h5` downloads run on `NODES_POOL` (4 threads), so a few large-circuit requests cannot hold every `FETCH_POOL` thread while other requests' small fetches wait. Files are fetched with the circuit's `Asset` object, not its id: given an id, entitysdk fetches the asset metadata again before every file.

Measured against staging circuit `8176966b-cce1-45ef-9642-e87c4436ee7d` with "All biophysical neurons" (2 templates, 10 mod files), median of 6 runs:

| | Derivation path | Circuit files |
|---|---|---|
| One request | 3.04 s | 2.55 s |
| 4 concurrent requests, per request | 3.53 s | 2.80 s |
| Peak Python memory | 1.5 MB | 1.5 MB |
