---
tags:
  - circuit-simulation
---

# NEST Point Neuron Simulations

NEST simulations in OBI-ONE run point neuron networks from a SONATA-extension circuit (`target_simulator: "NEST"`, defined by the [`sonata_nest`](https://sonata-extension.readthedocs.io/) spec). Node populations are `point_neuron` / `point_process` / `virtual`, edge populations are `chemical`. NEST and NESTML are optional: install them with `pip install obi-one[nest]`. NEST needs no SONATA/HDF5 support, since `libsonata` reads the network files and the network is built through PyNEST. The code lives in `obi_one/scientific/library/simulation/nest/`.

## Loader

`NestSonataNetwork` reads the simulation and circuit configs through `libsonata` and mirrors the stock `nest.SonataNetwork` API:

```python
from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork

net = NestSonataNetwork("simulation_config.json")
net.BuildNetwork()         # Create() + Connect()
net.add_spike_recorders()  # one spike_recorder per non-virtual population
net.Simulate()             # runs for run.tstop ms
```

- **Point neurons** are created per model template with its `params`, then the per-node `dynamics_params` from the nodes file.
- **Virtual populations** become `spike_train_injector` nodes fed by the `synapse_replay` inputs targeting them.
- **Synapses** get the template's `model` and `params`, then per-edge `syn_weight`/`delay`, then per-edge `dynamics_params` (e.g. `U`, `u`, `tau_rec`, `tau_fac`, `receptor_type`).
- **Templates** are read as `<point_neuron_models_dir>/<model_template>.json`. The directory is set on each population in the circuit config, or once under `components` as a default for populations without their own (libsonata resolves the default). Node and edge populations that share a directory must use distinct template names.

`run_simulation(simulation_config, num_threads=1)` does all of the above and writes the spikes of every non-virtual population to the config's `output.spikes_file` as a SONATA spike report. Voltage `reports` are not supported and raise `NotImplementedError`.

## Simulation execution task

`circuit_simulation_nest_machine` is the launch-system task for NEST simulations, alongside the neurodamus and `brian2` machine tasks. It is selected when the simulation's (or circuit's) `target_simulator` is `NEST`. It stages the circuit and simulation config (reusing the neuron staging helper), calls `run_simulation` with one NEST thread per CPU in `JOB_CPUS` (one thread when it is unset), and registers the spike report as a `SimulationResult` (no voltage reports). It is built on the shared `SimulationExecutionTask`, which the neuron execution tasks also subclass; each subclass only provides circuit staging and the simulator-specific run step. NEST ignores `OMP_NUM_THREADS` and starts on one thread, so the loader sets `nest.local_num_threads` when it resets the kernel. The thread count is also the number of virtual processes, which NEST uses to seed its random number streams, so a model with random elements gives different results on a different number of CPUs. The kernel is seeded from the simulation config's `run.random_seed` plus one, because NEST rejects a seed of 0; a negative seed raises `ValueError`. With the same seed and the same number of CPUs, a random model repeats its spikes. It is billed with the `NEST_CIRCUIT_SIMULATION` service subtype, and its launch dependencies are `launch_scripts/launch_task_for_single_config_asset/dependencies/nest.txt` (`obi-one[nest]`).

## NESTML custom models

A template whose `model` is `nestml:<name>` references `<point_neuron_models_dir>/<name>.nestml`. On first use the loader runs NESTML to generate and compile a NEST extension module, installs it and creates nodes with the generated model. Modules are cached by source hash under `<circuit>/.nestml_cache/`. The host needs `cmake`, `make` and a C++ compiler. Build failures raise `NestmlBuildError` with the path to the build output. Co-generated plastic (STDP) neuron/synapse pairs are not supported yet.

NESTML builds against the NEST in the environment, using the `nest-config` of `nest.build_info['prefix']`, so NEST must be compile-capable: the NEST runtime image, or a source or conda build. The PyPI `nest-simulator` wheel is not supported. obi-one does not check for Boost or GSL headers; the environment must provide them. Models whose ODEs have no analytic solution (e.g. AdEx) are integrated with GSL and need its headers.
