---
tags:
  - circuit-simplification
---

# Circuit Simplification

Circuit simplification produces a reduced, simulatable SONATA circuit from a biophysically detailed parent circuit using the [sonata-simplify](https://github.com/openbraininstitute/sonata-simplify) pipeline (requires `sonata-simplify>=0.2.6` and `bluecellulab>=2.6.108`). Each selected algorithm registers one derived `Circuit` entity, linked to the parent by a `circuit_simplification` derivation.

## Key Components

### CircuitSimplificationScanConfig

The `CircuitSimplificationScanConfig` class (located in `obi_one/scientific/tasks/circuit_simplification/config.py`) is UI-enabled and configures the simplification. It includes:

- **Initialize**: the parent `Circuit` entity, and an optional **Target Neuron Set** reference. The pipeline uses as many worker processes as the launch system allocated (`JOB_CPUS`), or 1 when run locally.
- **Neuron Sets**: a dictionary of biophysical neuron set blocks (e.g. by e-type or m-type via property neuron sets) that the target neuron set can reference. Without a target neuron set all biophysical neurons are simplified. A target neuron set is only accepted when every selected algorithm supports partial simplification (currently `single_compartment`); otherwise config validation fails.
- **Algorithms**: a dictionary of simplification algorithm blocks. Each block names one algorithm to run; the registered output circuit is named `<parent>__<campaign>__<algorithm>`.

### Supported algorithms

The available algorithm blocks map to a base algorithm in sonata-simplify plus an optional exporter (`ALGORITHM_EXPORT_MAP` in `obi_one/scientific/tasks/circuit_simplification/algorithms/metadata.py`):

- `single_compartment` — reduces each biophysical cell to a single compartment with Rössert synaptic correction filters; output stays NEURON-compatible. Options: `filter_poles` (1-4, scannable; 1 and 2 use dedicated ProbFilt mods, 3-4 the zero-padded 5-pole mods), `filter_method` (`timedomain` or the faster passive `impedance` approximation) and `strict_filters` (default on, so failed filter fits fail the task instead of falling back to pass-through filters).
- `lif_nest`, `adex_nest`, `adex_brian2`, `izhikevich_nest`, `glif_nest`, `gif_nest` — convert cells to point-neuron models and export the circuit to NEST or Brian2 SONATA format.
- `neuron_reduce` — impedance-based morphology reduction to reduced multi-compartment ME-models (Amsalem et al. 2020); NEURON output.
- `neat_reduction` (experimental) — NEAT compartment reduction preserving transfer impedance at selected fit locations; NEURON output.

`neuron_reduce` and `neat_reduction` need the `reduction` extra of sonata-simplify, which is installed in the launch environment (`circuit_simplification.in`) but not in the default local install.

Each output circuit is smoke-checked for BluePySnap loadability before registration. The simulator-specific output (`target_simulator` in the exported `circuit_config.json`, defaulting to NEURON) determines the registered entity's target simulator. For provenance, the versions of `obi-one`, `sonata-simplify` and `bluecellulab` are appended to the registered circuit's description and written, together with the algorithm parameters, to `simplification_provenance.json` next to the output `circuit_config.json`.

Resource estimation (`app/services/resource_estimation/circuit_simplification.py`) sizes filter (`single_compartment`), morphological-reduction (`neuron_reduce`, `neat_reduction`) and point-neuron algorithms on separate tiers; cores follow the most demanding selected algorithm and the time limit adds up over algorithms, since they run sequentially.

## Local Notebook

Open `examples/obi_one/scientific/tasks/circuit_simplification/run_simplification_local.ipynb` using a kernel with the optional simplification dependencies installed (`make install-simplification`). The notebook defaults to a local circuit and does not authenticate or register remote entities. Each run writes into a fresh directory under `obi-output/circuit_simplification/` outside the repository, leaving previous runs and input circuits unchanged.

Set `OBI_SIMPLIFICATION_CIRCUIT` to use a different local circuit and `SIMPLIFICATION_ALGORITHM=neat_reduction` to exercise NEAT. The optional direct exports and simulator checks are disabled by default; enable `RUN_EXPORTS` explicitly. Brian2 requires a recurrent circuit with one non-virtual node population and one edge population. Staging access and remote registration are separate opt-in settings.
