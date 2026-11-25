---
tags:
  - circuit-simulation
---

# NEST Point Neuron Simulations

NEST simulations in OBI-ONE run point neuron networks from a SONATA-extension circuit (`target_simulator: "NEST"`, defined by the [`sonata_nest`](https://sonata-extension.readthedocs.io/) spec). Node populations are `nest_point` / `virtual`, edge populations are `nest_chemical`, and `/0/model_type` of a node population equals its `type`. NEST and NESTML are optional: install them with `pip install obi-one[nest]`. NEST needs no SONATA/HDF5 support, since `libsonata` reads the network files and the network is built through PyNEST. The code lives in `obi_one/scientific/library/simulation/nest/`.

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
- **Virtual populations** get no NEST nodes. Each `synapse_replay` input delivers the spikes of every population in its spike file through the edge populations whose source is that population, to the targets in the input's `node_set` (as for the other simulators). The source can be a virtual population or a simulated one, whose spikes are then replayed through its own edges on top of its activity.
- **Replay** creates one `spike_train_injector` per input, population and source node that has spikes in `[delay, delay + duration)`; the spike times are not shifted. The injectors are in `NestSonataNetwork.replay_collections`. An input whose node set contains no target of those edges raises a `ValueError`, and one without spikes in the window logs a warning.
- **Synapses** get the template's `model` and `params`, then per-edge `syn_weight`/`delay`, then per-edge `dynamics_params` (e.g. `U`, `u`, `tau_rec`, `tau_fac`, `receptor_type`). Edges are connected with one `nest.Connect` call per template, passing the per-edge values as arrays.
- **Current clamps**: `linear`, `pulse` and `sinusoidal` inputs inject their current (nA in the config, pA in NEST) into the `nest_point` nodes of their `node_set` through a `dc_generator`, `step_current_generator` or `ac_generator`. Times are rounded to steps of `run.dt`, and a window that starts before the second step starts there. Currents on the same node add up.
- **Reports**: enabled soma reports of `v` are recorded with one `multimeter` per population and written to the report's `file_name` as SONATA soma reports, readable with `libsonata.SomaReportReader`. `run_simulation` runs NEST one minimum delay past `tstop` after the spikes are collected, because a multimeter delivers its samples that late; the spike report keeps only the spikes up to `tstop`.
- **Connection overrides**: `weight` is a factor on the circuit weight of each synapse, including the synapses of the spike replays, so overrides do not compound. `synapse_delay_override` replaces the delay, and `delay` is the time at which the override takes effect (a multiple of `run.dt`): the simulation is split there. Other fields are errors.
- **Ignored**: `conditions`, `run.spike_threshold`, `run.integration_method`, `run.nsteps_block` and `represents_physical_electrode` log a warning and are ignored.
- **Templates** are read as `<point_neuron_models_dir>/<model_template>.json`. The directory is set on each population in the circuit config, or once under `components` as a default for populations without their own (libsonata resolves the default). Node and edge populations that share a directory must use distinct template names. The names in `params` and `dynamics_params` must be parameters of the NEST model (`nest.GetDefaults(<model>)` lists them). Before any node or synapse is created, the loader raises a `ValueError` that names the population, the template, the model and the unknown names.

`run_simulation(simulation_config, num_threads=1, nestml_cache_dir=None)` does all of the above and returns `SimulationResults`: the spikes of every non-virtual population in the config's `output.spikes_file`, as a SONATA spike report, and the soma reports.

## Simulation campaigns

NEST simulation campaigns are configured with `NestCircuitSimulationScanConfig` (or `NestCircuitSimulationSingleConfig` for a single coordinate) in `obi_one/scientific/tasks/generate_simulations/config/nest/`, the NEST counterpart of the Brian2 config. It emits a `simulation_config.json` with `target_simulator: "NEST"` and `run.dt` 0.025 ms, and is served at `/generated/nest-circuit-simulation-scan-config-generate-grid`. Generating a campaign does not need NEST; running one does. The circuit must have a `nest_point` population, and no node populations other than `nest_point` and `virtual` ones.

The config reuses the shared blocks, restricted to what the runner executes:

| Kind | Blocks |
| --- | --- |
| Stimuli | `ConstantCurrentClampSomaticStimulus`, `LinearCurrentClampSomaticStimulus`, `MultiPulseCurrentClampSomaticStimulus`, `SimulationDtSinusoidalCurrentClampSomaticStimulus`, and the five spike stimuli (`synapse_replay`) |
| Recordings | `SomaVoltageRecording`, `TimeWindowSomaVoltageRecording`, and their simulation-timestep variants |
| Synaptic manipulations | `ConnectSynapticManipulation`, `DisconnectSynapticManipulation`, `ScaleWeightSynapticManipulation` |
| Neuron sets | point and virtual neuron sets |

`SinusoidalCurrentClampSomaticStimulus` is not offered, because NEST samples a sinusoid on the simulation timestep and would ignore its Timestep. Noise, Ornstein-Uhlenbeck, threshold-relative, voltage clamp and electric field stimuli have no NEST module in the spec. The initial voltage and the simulation's neuron set are hidden: NEST ignores `conditions`, and the simulation runs on all point neurons.

Every untargeted block falls back to `"Default: All Point Neurons"`, except the source of a spike stimulus. When every virtual population of the circuit projects onto a point population, an untargeted spike source is `"Default: All Virtual Neurons"`: the virtual populations of a simplified circuit are its projections, which stay silent unless spikes are replayed from them. Otherwise the source is the point neurons. A manipulation's presynaptic set falls back to the point neurons like the other blocks, so a manipulation of the projections names a virtual neuron set.

Generation refuses, before anything is written, what the runner would refuse once launched:

- a circuit with populations other than `nest_point` and `virtual`, or without a `nest_point` population;
- a recording whose Timestep is not a multiple of 0.025 ms;
- a synaptic manipulation timed between two steps;
- a pulse longer than its period;
- a current clamp whose neuron set contains no `nest_point` neuron;
- recordings over the memory limit.

The connection override and pulse checks call the runner's own parsing (`connection_overrides.parse_overrides`, `current_clamps.pulse_steps`), and the recording frames come from `soma_reports.Frames`, so generation and the runner agree.

Each recording has its own multimeter, sampled on its own Timestep over its own window, and NEST holds every sample until the run ends. Generation adds up neurons x frames over the recordings and refuses more than `MAX_NEST_RECORDED_SAMPLES` (4e7). The limit was measured with `simulate_nest` on circuits of unconnected neurons: about 104 bytes of peak memory per sample, so 4e7 samples take 4.2 GB of the job's 8 GB. A recording without a neuron set records every point neuron; a smaller neuron set, a shorter window or a coarser Timestep records fewer samples.

The config adds two hooks to `BaseSimulationScanConfig`, which the other simulators keep as no-ops: `default_spike_source_population_type`, the population type an untargeted spike source defaults to, and `validate_sonata_config`, called by the generation task once the inputs, reports and connection overrides are assembled.

`examples/obi_one/scientific/tasks/generate_simulations/NEST/nest_circuit_simulation.ipynb` is a worked example. It builds a campaign with these blocks for the NEST export of a simplified circuit (by default the newest export written by `run_simplification_local.ipynb`), generates the SONATA config, shows a refusal at generation, and runs the simulation with `run_simulation`.

## Simulation execution task

`circuit_simulation_nest_machine` is the launch-system task for NEST simulations, alongside the neurodamus and `brian2` machine tasks. It is selected when the simulation's (or circuit's) `target_simulator` is `NEST`. It stages the circuit and simulation config (reusing the neuron staging helper), calls `run_simulation` with one NEST thread per CPU in `JOB_CPUS` (one thread when it is unset), and registers the spike report and the soma reports as a `SimulationResult`. It is built on the shared `SimulationExecutionTask`, which the neuron execution tasks also subclass; each subclass only provides circuit staging and the simulator-specific run step. NEST ignores `OMP_NUM_THREADS` and starts on one thread, so the loader sets `nest.local_num_threads` when it resets the kernel. The thread count is also the number of virtual processes, which NEST uses to seed its random number streams, so a model with random elements gives different results on a different number of CPUs. The kernel is seeded from the simulation config's `run.random_seed` plus one, because NEST rejects a seed of 0; a negative seed raises `ValueError`. With the same seed and the same number of CPUs, a random model repeats its spikes. It is billed with the `NEST_CIRCUIT_SIMULATION` service subtype, and its launch dependencies are `launch_scripts/launch_task_for_single_config_asset/dependencies/nest_image.txt` (`obi-one[nest]`). The `nest_image.override` next to it pins `nest-simulator`, which the launch-system `python3.12-compiler-nest` runtime builds from source at that version, with NESTML at the version in `nest_image.txt`; both are read at the obi-one release the image is built for.

## NESTML custom models

A template whose `model` is `nestml:<name>` references `<point_neuron_models_dir>/<name>.nestml`. On first use the loader runs NESTML to generate and compile a NEST extension module, installs it and creates nodes with the generated model. Modules are cached by source hash under the `nestml_cache_dir` given to `NestSonataNetwork` or `run_simulation`, by default `<circuit>/.nestml_cache/`. The simulation execution task passes `<coordinate_output_root>/nestml_cache`, because the staged circuit can be a read-only asset mount on the launch-system executors. The host needs `cmake`, `make` and a C++ compiler. Build failures raise `NestmlBuildError` with the path to the build output. Co-generated plastic (STDP) neuron/synapse pairs are not supported yet.

NESTML builds against the NEST in the environment, using the `nest-config` of `nest.build_info['prefix']`. The NEST runtime image, a source build and a conda build have a valid prefix and are used as they are. The PyPI `nest-simulator` wheel runs NEST, but its `nest-config` and `build_info['prefix']` point into the temporary directory the wheel was built in, and it uses the pre-C++11 `std::string` ABI. For the wheel, `nestml_build.nest_prefix` writes a `nest-config` wrapper next to the build output that sets the compiler (`CXX`, else `c++`), the include path, no libraries and the ABI flag, and passes every other option to the wheel's `nest-config`. The wheel therefore works for local testing, and needs a C++ compiler, CMake and the Boost and GSL headers on the host. See [nest-simulator#3762](https://github.com/nest/nest-simulator/issues/3762#issuecomment-4448756028) and [nestml#1384](https://github.com/nest/nestml/issues/1384) for the upstream reports; the ABI mismatch is not reported there. obi-one does not check for Boost or GSL headers; the environment must provide them. Models whose ODEs have no analytic solution (e.g. AdEx) are integrated with GSL and need its headers.
