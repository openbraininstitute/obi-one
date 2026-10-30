---
tags:
  - circuit-simulation
---

# Neuronal Manipulation Properties

`POST /circuit-neuronal-manipulation-properties-by-neuron-set` returns the mechanism variables a neuronal manipulation block can change for the neurons of a neuron set: per ion channel, its section lists and, per variable, its units, limits, type (RANGE or GLOBAL) and original value per section list. The UI builds its variable picker from this response.

The variables are read from the files inside the circuit's `sonata_circuit` asset. No `emodel_circuit` derivation is needed, so a registered, extracted or customised circuit works as soon as it has its hoc and mod files.

## Data flow

1. Stage `circuit_config.json`. With a neuron set, stage `node_sets.json` and the `nodes.h5` of every population concurrently; the neuron set may name any population. Without one, only the `model_template` column of each biophysical population is needed, so each `nodes.h5` is read the cheapest way available (see [Reading `model_template` without a neuron set](#reading-model_template-without-a-neuron-set)).
2. Resolve the neuron set to node IDs per population, and read `model_template` for those nodes. Without a neuron set, take every distinct `model_template` of every biophysical population.
3. For each template, fetch `<biophysical_neuron_models_dir>/<name>.hoc` and read two procedures:
   - `insertChannel()`: which mechanism is inserted in which section list.
   - `biophys()`: the value of each variable per section list.
4. List the asset once (`list_directory`, started together with the config fetch; the same listing gives the `nodes.h5` sizes below) and fetch every `.mod` file of `<mechanisms_dir>` (a few dozen small files, in the same concurrent batch as the hoc files). Each is indexed by the `SUFFIX` in its `NEURON` block, and each inserted mechanism that is not a NEURON built-in is looked up there to read its `RANGE` and `GLOBAL` variable names and the units declared in `PARAMETER`, `ASSIGNED` or `STATE` (a block that appears twice, as in `StochKv3.mod`, is read in full; comments, including `COMMENT ... ENDCOMMENT` blocks, are ignored). A variable whose mod file declares no unit (the rCA1 circuits have 15, such as `tau_kmb`) takes it from the ion channel model entities with the same `nmodl_suffix`: one search per such suffix, all at once. An entity counts only when every unit it shares with the mod file is equal (`mho` and `S` are the same), and the unit is used only when all those entities agree; otherwise it stays empty. A failed search leaves the unit empty and is logged. When the config declares no `mechanisms_dir`, the first of `mod/` (OBI circuits) and `mechanisms/` (circuits staged by entitysdk from an MEModel) that holds a `.mod` file is used.
5. Build each template's variables, then keep only the channels, variables and section lists common to all templates in the selection.

NEURON names a mechanism by the `SUFFIX` inside its mod file, not by the file name: rCA1 keeps `kdrb` in `kdrbca1.mod` and `hd` in `h.mod`, and simulates fine. Looking a mechanism up by file name would miss those, so the whole directory is read and indexed by `SUFFIX` instead; the index is built once per request and shared by every template. A mechanism no file defines, or two files define, fails its template.

NEURON's built-in mechanisms have no mod file. `pas`, `fastpas`, `hh` and `extracellular` get their settable `RANGE` variables and units from a table in the reader. `capacitance` and the ion mechanisms (`na_ion`, `k_ion`, ...) add no variable: `cm` is already a section property, and `ena` or `ek` are set directly in `biophys()`.

## Hoc reader

The hoc files are printed by the BluePyEModel cell template (`cell_template_neurodamus_*.jinja2`, format in the [SONATA extension](https://sonata-extension.readthedocs.io/en/latest/hoc-emodel.html)). Inside `insertChannel()` and `biophys()` that template prints only three line shapes, and the reader accepts only these:

```text
forsec this.<section_list> { insert <mechanism> }
forsec CellRef.<section_list> { <variable> = <number> }
distribute_distance(CellRef.<section_list>, "<variable>", "<formula>")
```

For `distribute_distance`, the value is the optimised parameter BluePyOpt substituted for `{value}`, which is what the derivation path shows. Every built-in BluePyEModel distribution has one of two shapes: a product where `{value}` is the only plain-number factor (`exp`, `exp_na_dend`, `linear_hd_apic`, `sigmoid_kad_apic`, `linear_hdpas` end with `*{value}`, `step` starts with `{value} *`), or `linear_e_pas_apic`, `({value}-5*{distance}/150)`. Any other formula, such as a sum with a function or two plain-number factors, has no single reading and gives `null` and a warning. The value of a mechanism `GLOBAL` variable is the one the template checks in `proc check_simulator()`. Any other line rejects the template; nothing is guessed. A test renders a hoc file with the real template and checks the reader returns the input values.

## Fallback and errors

A template is read from the derivation path instead, with a warning naming the reason, when its hoc file is missing, too large (over 1 MB) or not template output, when no mod file defines one of its mechanisms (or two do), when the asset cannot be listed, or when its population has no `biophysical_neuron_models_dir`. Warnings quote only the reader's own messages; fetch errors are logged and reported by type only, since they can contain signed storage URLs.

A circuit without exactly one `sonata_circuit` asset is rejected (HTTP 400) with or without a neuron set.

Asset paths built from circuit content are refused when absolute or containing `..`.

## Differences from the derivation path

| Field | Circuit files | Derivation path |
|---|---|---|
| Section lists of a channel | where `insertChannel()` inserts it | where the optimisation output has a parameter |
| Variable names | `RANGE` / `GLOBAL` of the circuit's mod file | `neuron_block` of the ion channel model entity |
| `units` | from the mod `PARAMETER`, `ASSIGNED` or `STATE` block, else from the ion channel model entity with the same suffix | often empty |
| Values not optimised (`cm`, `Ra`, some `vshift*`) | read from `biophys()` | `null` |
| Channel `entity_id` | `null` (the UI hides the channel link) | ion channel model ID |

The circuit's mod files are the ones the simulation compiles. When they differ from the ion channel model entity's mod file, the two paths list different variables.

## Reading `model_template` without a neuron set

A `nodes.h5` can be large (743 MB for nbS1, 4.2 million nodes) while the distinct `model_template` values it holds are a few dozen strings. Without a neuron set nothing else of the file is needed, so each biophysical population is read in the first way that works:

1. A symlink to the mounted asset store (`FetchFileStrategy.link_only`), free when the API runs with `MOUNT_BASE_DIR`.
2. Byte ranges of the file in storage. entitycore answers the download endpoint with a redirect to a presigned storage URL, and storage serves `Range` requests. `obi_one.utils.http_range_file.HttpRangeFile` turns that URL into a file object, given the file size from the asset listing. No `HEAD` request is sent: S3 refuses `HEAD` with 403 on a presigned URL signed for `GET` (every `entitycore-data-staging` file checked on staging), while a `Range` `GET` on the same URL answers 206. A first read not answered with 206, or a body of the wrong length, counts as a failure and leads to the download below. The listing size matched the storage size on all 20 `nodes.h5` files checked, up to 743 MB. and `obi_one.db_sdk.assets.open_asset_h5` opens it with h5py, which then reads only the metadata it needs plus the `model_template` column and its `@library`. Reads under 4 MB are rounded to 4 MB blocks that are kept for the life of the file object, so the HDF5 metadata costs a few requests and the column costs one. entitysdk has no method returning the redirect URL; that is flagged for entitysdk, and until then the client's own HTTP client and token are reused.
3. The full download, when storage does not redirect or does not serve ranges (with a warning), or when the listing failed and the size is unknown.

Measured on staging, one run each:

| | nbS1 | rCA1 |
|---|---|---|
| `nodes.h5` size | 743 MB | 59 MB |
| Bytes read | 33.7 MB | 26.8 MB |
| Range requests | 5 | 6 |
| Time to the template set | 6.3 s | 7.2 s |
| Full download before | about 45 s | about 15 s |

All three ways read the column with the same h5py function, so a local file and a remote one give the same set by construction. For an enumerated column it reads the small integers and looks up the distinct ones in `@library`, never one string per node.

With a neuron set the file is still staged whole: resolving a node set to node IDs reads other columns through bluepysnap and libsonata, which need a local file.

## Concurrency

Files are fetched with the `Asset` object of the circuit, not its id: given an id, entitysdk fetches the asset's metadata again before every file, which was a third of all requests. File fetches run on `FETCH_POOL`, one thread pool shared by every request in the process, capped at 16 threads. The cap bounds threads and concurrent requests to entitycore and storage however many requests arrive; extra fetches queue. Each fetch is an API call, a redirect and a storage download, so threads mostly wait on the network.

Measured against staging circuit `8176966b-cce1-45ef-9642-e87c4436ee7d` with "All biophysical neurons" (2 templates, 10 mod files), median of 6 runs:

| | Derivation path | Circuit files |
|---|---|---|
| One request | 3.04 s | 2.55 s |
| 4 concurrent requests, per request | 3.53 s | 2.80 s |
| Peak Python memory | 1.5 MB | 1.5 MB |
