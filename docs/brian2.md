---
tags:
  - circuit-simulation
---

# Brian2 Point Neuron Simulations

Brian2 simulations in OBI-ONE run point neuron networks from a SONATA circuit, targeting the
[Brian2](https://brian2.readthedocs.io/) simulator instead of NEURON. They are configured with
`Brian2CircuitSimulationScanConfig` (or `Brian2CircuitSimulationSingleConfig` for a single
coordinate), which emits a `simulation_config.json` with `target_simulator: "Brian2"`.

The generated config is executed by
`obi_one/scientific/library/simulation/brian2/simulate_brian2.py`, which translates the SONATA
config into a Brian2 network.

## Overview

A Brian2 simulation differs from a NEURON circuit simulation in a few important ways:

- **Point neurons, not biophysical ones**: the circuit carries one point node population whose
  neuron and synapse models are supplied as templates in `point_neuron_models_dir`. There are no
  morphologies, so nothing can be targeted per-compartment.
- **A single node population**: virtual populations are not supported.
- **One integration timestep**: everything the simulation samples or plays back is clocked by
  `run.dt`.

## Reused blocks

The Brian2 config composes the same blocks as the other simulation configurations, restricted to
what the runner can execute.

### Stimuli

| Block | SONATA module |
| --- | --- |
| `Brian2DirectPoissonStimulus` | `poisson` |
| `ConstantCurrentClampSomaticStimulus` | `linear` |
| `LinearCurrentClampSomaticStimulus` | `linear` |
| `MultiPulseCurrentClampSomaticStimulus` | `pulse` |
| `Brian2SinusoidalCurrentClampSomaticStimulus` | `sinusoidal` |

The current injections are played into the neurons as a `TimedArray` and summed per target
neuron set. `Brian2DirectPoissonStimulus` instead kicks the membrane potential directly, bypassing
the circuit's synapses.

Stimuli that scale with a cell's threshold current (the relative variants), noise, Ornstein-
Uhlenbeck, electric field and voltage clamp modules have no Brian2 counterpart and are not
offered. Spike stimuli are excluded too: the runner reads a `synapse_replay` input's `node_set` as
a filter on which *source* spikes to replay, which is not the target semantics the spike stimulus
blocks emit.

### Recordings

| Block | Notes |
| --- | --- |
| `Brian2SomaVoltageRecording` | Full length of the experiment |
| `Brian2TimeWindowSomaVoltageRecording` | Restricted to a start and end time |

These are the counterparts of `SomaVoltageRecording` and `TimeWindowSomaVoltageRecording`, minus
the **Timestep** parameter. Brian2 samples its `StateMonitor` on the integration timestep and
rejects a report asking for any other interval, so the recording's sampling interval is the
simulation timestep rather than a parameter of its own. The same applies to the sinusoidal
stimulus, which is why `Brian2SinusoidalCurrentClampSomaticStimulus` has no Timestep either.

Only soma voltage (`variable_name: "v"`) is reported.

### Synaptic manipulations

| Block | Notes |
| --- | --- |
| `ConnectSynapticManipulation` | Sets the weight of every synapse between two neuron sets |
| `DisconnectSynapticManipulation` | Sets that weight to zero |

Both become SONATA `connection_overrides`, applied part-way through the run at the timestamps the
block references. Brian2 honours a connection override's `weight` and `synapse_delay_override`,
and raises on `spont_minis`, `synapse_configure`, `modoverride` and the neuromodulation fields —
so the mechanism-specific manipulations (`SynapticMgManipulation`,
`ScaleAcetylcholineUSESynapticManipulation`) are not offered.

### Neuron sets and timestamps

Neuron sets are restricted to the point-neuron sets (`Brian2SimulationNeuronSetUnion`). Timestamps
blocks are shared with the other simulation configurations and are referenced by the current
injections and the synaptic manipulations.

## Defaults

An untargeted block falls back to the simulation-wide default neuron set,
`"Default: All Point Neurons"`, which covers every point neuron in the circuit.

The one exception is `Brian2DirectPoissonStimulus`: an untargeted Direct Poisson input instead
drives `"Default: Sugar gustatory receptor neurons"`, the `sugar` node set stimulated by the Shiu
et al. (2024) FlyWire model. That set is small enough to stay under the block's neuron limit,
which the whole circuit would exceed.
