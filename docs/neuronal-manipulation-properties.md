---
tags:
  - circuit-simulation
---

# Neuronal Manipulation Properties

`POST /circuit-neuronal-manipulation-properties-by-neuron-set` returns the mechanism variables a neuronal manipulation block can change for the neurons of a neuron set: per ion channel, its section lists and, per variable, its units, limits, type (RANGE or GLOBAL) and original value per section list. The UI builds its variable picker from this response.

The variables are read from the files inside the circuit's `sonata_circuit` asset. No `emodel_circuit` derivation is needed, so a registered, extracted or customised circuit works as soon as it has its hoc and mod files.

## Data flow

1. Stage `circuit_config.json`, then `node_sets.json` and every `nodes.h5` concurrently.
2. Resolve the neuron set to node IDs per population, and read `model_template` for those nodes. Without a neuron set, take every distinct `model_template` of every biophysical population.
3. For each template, fetch `<biophysical_neuron_models_dir>/<name>.hoc` and read two procedures:
   - `insertChannel()`: which mechanism is inserted in which section list.
   - `biophys()`: the value of each variable per section list.
4. Fetch `<mechanisms_dir>/<mechanism>.mod` for each inserted mechanism except `pas`, and read its `RANGE` and `GLOBAL` variable names and the units declared in `PARAMETER`.
5. Build each template's variables, then keep only the channels, variables and section lists common to all templates in the selection.

## Hoc reader

The hoc files are printed by the BluePyEModel cell template (`cell_template_neurodamus_*.jinja2`, format in the [SONATA extension](https://sonata-extension.readthedocs.io/en/latest/hoc-emodel.html)). Inside `insertChannel()` and `biophys()` that template prints only three line shapes, and the reader accepts only these:

```text
forsec this.<section_list> { insert <mechanism> }
forsec CellRef.<section_list> { <variable> = <number> }
distribute_distance(CellRef.<section_list>, "<variable>", "<formula>")
```

For `distribute_distance`, the value is the factor the formula is multiplied by, which is the optimised value. Any other line rejects the template; nothing is guessed. A test renders a hoc file with the real template and checks the reader returns the input values.

## Fallback and errors

A template is read from the derivation path instead, with a warning naming the reason, when its hoc or mod file is missing, too large (over 1 MB) or not template output, or when its population has no `biophysical_neuron_models_dir` or `mechanisms_dir`. Warnings quote only the reader's own messages; fetch errors are logged and reported by type only, since they can contain signed storage URLs.

Asset paths built from circuit content are refused when absolute or containing `..`.

## Differences from the derivation path

| Field | Circuit files | Derivation path |
|---|---|---|
| Section lists of a channel | where `insertChannel()` inserts it | where the optimisation output has a parameter |
| Variable names | `RANGE` / `GLOBAL` of the circuit's mod file | `neuron_block` of the ion channel model entity |
| `units` | from the mod `PARAMETER` block | often empty |
| Values not optimised (`cm`, `Ra`, some `vshift*`) | read from `biophys()` | `null` |
| Channel `entity_id` | `null` (the UI hides the channel link) | ion channel model ID |

The circuit's mod files are the ones the simulation compiles. When they differ from the ion channel model entity's mod file, the two paths list different variables.

## Concurrency

File fetches run on `FETCH_POOL`, one thread pool shared by every request in the process, capped at 16 threads. The cap bounds threads and concurrent requests to entitycore and storage however many requests arrive; extra fetches queue. Each fetch is an API call, a redirect and a storage download, so threads mostly wait on the network.

Measured against staging circuit `8176966b-cce1-45ef-9642-e87c4436ee7d` with "All biophysical neurons" (2 templates, 10 mod files), median of 6 runs:

| | Derivation path | Circuit files |
|---|---|---|
| One request | 3.04 s | 2.55 s |
| 4 concurrent requests, per request | 3.53 s | 2.80 s |
| Peak Python memory | 1.5 MB | 1.5 MB |
