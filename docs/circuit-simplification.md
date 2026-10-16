---
tags:
  - circuit-simplification
---

# Circuit Simplification

Circuit simplification produces a reduced, simulatable SONATA circuit from a biophysically detailed parent circuit using the [sonata-simplify](https://github.com/openbraininstitute/sonata-simplify) pipeline. Each selected algorithm runs over all biophysical node populations of the parent circuit and registers one derived `Circuit` entity per algorithm, linked to the parent by a `circuit_simplification` derivation.

## Key Components

### CircuitSimplificationSingleConfig

The `CircuitSimplificationSingleConfig` class (located in `obi_one/scientific/tasks/circuit_simplification/task.py`) configures the simplification. It includes:

- **Circuit**: The parent `Circuit` entity to simplify.
- **Algorithms**: A dictionary of simplification algorithm blocks. Each block names one algorithm to run; the registered output circuit is named `<parent>__<campaign>__<algorithm>`.
- **Initialize**: Execution settings such as `n_processes`.

### Supported algorithms

The available algorithm blocks map to a base algorithm in sonata-simplify plus an optional exporter (`ALGORITHM_EXPORT_MAP` in `obi_one/scientific/blocks/simplification_algorithms/metadata.py`):

- `single_compartment` — reduces each biophysical cell to a single compartment; output stays NEURON-compatible.
- `lif_nest`, `adex_nest`, `adex_brian2`, `izhikevich_nest`, `glif_nest`, `gif_nest` — convert cells to point-neuron models and export the circuit to NEST or Brian2 SONATA format.
- `neuron_reduce` — impedance-based morphology reduction to reduced multi-compartment ME-models (Amsalem et al. 2020); output stays NEURON-compatible. Requires a sonata-simplify release that carries the `reduction` extra (`sonata-simplify[reduction]`).

Each output circuit is smoke-checked for BluePySnap loadability before registration. The simulator-specific output (`target_simulator` in the exported `circuit_config.json`) determines the registered entity's target simulator.
