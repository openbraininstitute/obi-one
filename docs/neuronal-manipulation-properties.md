---
tags:
  - circuit-simulation
---

# Neuronal Manipulation Properties

`POST /circuit-neuronal-manipulation-properties-by-neuron-set` returns the mechanism variables a neuronal manipulation block can change for the neurons of a neuron set: per ion channel, its section lists, its ion channel model `entity_id` and, per variable, its units, limits, type (RANGE or GLOBAL) and original value per section list. The UI builds its variable picker from this response. The response's `source` says where the variables come from: `circuit_files`, `derivations`, or `mixed` when only some templates fall back (see below); it is `null` when no template has variables.

The variables are read from the hoc and mod files inside the circuit's `sonata_circuit` asset. No `emodel_circuit` derivation is needed, so any circuit with those files works.

## Data flow

1. Stage `circuit_config.json`. With a neuron set, also stage the node sets file and the `nodes.h5` of every population. Without one, only the `model_template` column of each biophysical population is read (see below).
2. Resolve the neuron set to node IDs per population and read their `model_template`. Selected neurons of a population that is not `biophysical` (point neurons, as in Allen-V1) have no mechanism variables: they are left out with one warning, and their population is still listed in `populations`. A list in a neuron set field is a scan dimension (`node_set: ["L1_LAC", "L2_IPC"]`): each single-valued copy is resolved and the node IDs are unioned (`get_expanded_neuron_ids`, at most 100 combinations, top-level fields only). `/circuit/{circuit_id}/neuron-set-node-ids` returns the same union.
3. For each template, read `<biophysical_neuron_models_dir>/<name>.hoc`: `insertChannel()` says which mechanism is inserted in which section list, `biophys()` the value of each variable there.
4. List the asset once and fetch every `.mod` file of `<mechanisms_dir>` (or the first of `mod/`, `mechanisms/` that holds one). NEURON names a mechanism by the `SUFFIX` inside the file, not the file name (rCA1 keeps `kdrb` in `kdrbca1.mod`), so the whole directory is indexed by `SUFFIX`. Each mechanism gives its `GLOBAL` variables, its `RANGE` variables that are also in `PARAMETER`, and the units declared in `PARAMETER`, `ASSIGNED` or `STATE`. A `RANGE` name outside `PARAMETER` is computed by the mod file (a current such as `ina`, a `STATE` variable, or a conductance such as `gNaTg` that `BREAKPOINT` recomputes every step), so setting it changes nothing and it is not listed. On the 117 public BluePyEModel templates the hoc reader accepts, none of the 3,814 `RANGE` values their hoc files set is hidden by this rule.
5. Search the ion channel model entities once per distinct `SUFFIX` (`nmodl_suffix`, in parallel). An entity matches when every unit it shares with the mod file is equal (two mechanisms can share a suffix). The channel's `entity_id` is the matching entity when there is exactly one; with none or several it is `null`, and one warning names those mechanisms. A unit the mod file does not declare is taken from the matching entities when they all agree.
6. Keep the channels, variables and section lists common to all templates. A channel keeps its `entity_id` when every template gives the same one.

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

The fallback is per template. A template uses its `emodel_circuit` derivation when its hoc file is missing, over 1 MB or not template output, when a mechanism has no mod file (or two), or when its population declares no `biophysical_neuron_models_dir`. Templates with the same reason share one warning, which names the first five, for example "Circuit files: no mod file in the circuit defines mechanism 'NaTg'. Used the emodel_circuit derivation instead for 3 templates (a, b, c)." When a mod file the reader rejects may hold the missing mechanism, the reason names it. A template with no derivation either is left out of the intersection, and the warning says so. When some templates come from their files and others from derivations, `source` is `mixed`. Warnings quote only the reader's own messages; other errors are given by type, since they can hold signed storage URLs.

Without a neuron set, the whole request uses the derivations when the circuit has no single `sonata_circuit` asset, or when its config, a `nodes.h5` or a file entitycore serves cannot be read. Any other error is a bug and propagates.

These errors are raised instead of falling back:

- The asset cannot be listed (`list_directory` fails, usually a transient 503): HTTP 503, so the client can retry and get the circuit-file answer.
- A declared node sets file that fails for any reason other than 404 (outage, refused token): HTTP 500. A 404 is skipped, as with no node sets file at all.
- With a neuron set, a circuit without exactly one `sonata_circuit` asset, or a biophysical population without `model_template`: HTTP 400.

When two populations list one template with different model directories, the first population's files are used and one warning names the populations and templates.

In the logs, the credential parameters of presigned storage URLs (`X-Amz-Signature`, `X-Amz-Credential`, `X-Amz-Security-Token`) are replaced by `<redacted>`; the rest of the URL, such as entitycore search filters, stays readable. The filter (`obi_one.utils.log_redaction.RedactPresignedCredentials`) is installed on the root log handler in `app.application`, so it covers every logger that propagates to the root: httpx2, which logs every request URL at INFO, and entitysdk, which quotes the redirected URL in its errors. It does not cover Sentry, whose logging integration captures records before handler filters run, nor uvicorn's own loggers, which have their own handlers; those need a separate change. A malformed log call (a wrong number of `%s` arguments) is reported by logging as usual, with its arguments redacted.

A neuron set that selects no neurons is not an error. This happens, for example, with a node set copied from a larger circuit that has no cells in this one. The response has `populations: []`, no variables, and one warning naming the population and node sets, for example: "The neuron set selects no neurons in circuit 'rCA1-CYLINDER-REF-1PC-8PV-08' (population 'hippocampus_neurons'; node sets SLM_PPA, SO_BP, SO_BS), so there are no mechanism variables to list."

Asset paths built from circuit content are refused when absolute or containing `..`.

## Differences from the derivation path

| Field | Circuit files | Derivation path |
|---|---|---|
| Section lists of a channel | where `insertChannel()` inserts it | where the optimisation output has a parameter |
| Variable names | `RANGE` names also in `PARAMETER`, and `GLOBAL`, of the circuit's mod file | `neuron_block` of the ion channel model entity, computed conductances such as `gNaTg_NaTg` included |
| `units` | from the mod file, else from the ion channel model entity | often empty |
| Values not optimised (`cm`, `Ra`, some `vshift*`) | read from `biophys()` | `null` |
| Channel `entity_id` | the one ion channel model with the same `nmodl_suffix` and units, else `null` | ion channel model of the EModel |

The circuit's mod files are the ones the simulation compiles, so the two paths can list different variables.

## Switching the circuit-file path off

`NEURONAL_MANIPULATION_FROM_CIRCUIT_FILES` (default `true`) is read by the endpoint. Set to `false`, every template uses its derivation and no hoc or mod file is read, as before this feature: without a neuron set only the derivations are fetched, with one only the files needed to resolve it (`circuit_config.json`, node sets, `nodes.h5`). `source` is then `derivations`, and the only fallback warning names the templates without a derivation. It lets a deployment switch back without a revert.

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
