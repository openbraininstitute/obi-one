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
| `SimulationDtSinusoidalCurrentClampSomaticStimulus` | `sinusoidal` |
| `PoissonSpikeStimulus` and the other spike stimuli | `synapse_replay` |

The current injections are played into the neurons as a `TimedArray` and summed per target
neuron set. `Brian2DirectPoissonStimulus` instead kicks the membrane potential directly, bypassing
the circuit's synapses: every neuron in its target draws an independent Poisson train, from a
`brian2.PoissonGroup` with one source per targeted neuron, wired one-to-one onto it. Its cost
follows the size of the target, not how the target's node IDs are laid out. The spike stimuli
generate a spike file, which the runner replays through a `SpikeGeneratorGroup` wired with the
circuit's *own* connectivity.

A sinusoid has to be sampled fast enough to be represented, so
`SimulationDtSinusoidalCurrentClampSomaticStimulus` is refused when its frequency reaches the
Nyquist limit of the timestep it is sampled at — 20 kHz for Brian2's 0.025 ms. The limit is checked
when the configuration is generated rather than declared on the field, because the same block is
sampled at different timesteps in different simulations, and `SinusoidalCurrentClampSomaticStimulus`
sets its own with **Timestep**.

A spike stimulus's source neuron set says whose spikes are generated and replayed, and its target
says who receives them: the runner keeps the edges leading out of the spiking neurons and into the
target, so restricting the target narrows delivery without changing the spike trains. An unset
target covers every point neuron, delivering to everything the source projects onto.

Stimuli that scale with a cell's threshold current (the relative variants), noise, Ornstein-
Uhlenbeck, electric field and voltage clamp modules have no Brian2 counterpart and are not
offered.

Current amplitudes are nanoamps, as the blocks and SONATA's `current_clamp` inputs both describe
them. How much depolarisation that buys depends on the model's membrane resistance: against the
FlyWire model's 10 MΩ, 1 nA is worth about 10 mV.

### Recordings

| Block | Notes |
| --- | --- |
| `SimulationDtSomaVoltageRecording` | Full length of the experiment |
| `SimulationDtTimeWindowSomaVoltageRecording` | Restricted to a start and end time |

These are the counterparts of `SomaVoltageRecording` and `TimeWindowSomaVoltageRecording`, minus
the **Timestep** parameter. Brian2 samples its `StateMonitor` on the integration timestep and
rejects a report asking for any other interval, so the recording's sampling interval is the
simulation timestep rather than a parameter of its own. The same applies to the sinusoidal
stimulus, which is why `SimulationDtSinusoidalCurrentClampSomaticStimulus` has no Timestep either.

The blocks are named for this distinction rather than for Brian2: a `SimulationDt…` block is
clocked by the simulation timestep, and its counterpart adds an interval that can be set
independently. For recordings the two are separate branches of a shared `BaseRecording`,
`SimulationDtRecording` and `Recording`; `SinusoidalCurrentClampSomaticStimulus` instead derives
from `SimulationDtSinusoidalCurrentClampSomaticStimulus`. Nothing about the `SimulationDt…` blocks
is Brian2-specific, so any simulator with the same constraint can use them.

Only soma voltage (`variable_name: "v"`) is reported.

A recording holds the samples from its start time up to, but not including, its end time, so a window from 0 to 50 ms at 0.025 ms is 2,000 frames, as SONATA readers such as libsonata expect.
A start or end time between two samples is rounded to the nearest one, and the report's `mapping/time` gives the times of the frames actually written.

### Synaptic manipulations

| Block | Notes |
| --- | --- |
| `ConnectSynapticManipulation` | Restores the circuit's own weight of every synapse between two neuron sets |
| `DisconnectSynapticManipulation` | Sets that weight to zero |

Both become SONATA `connection_overrides`, applied part-way through the run at the timestamps the
block references. Brian2 honours a connection override's `weight` and `synapse_delay_override`,
and raises on `spont_minis`, `synapse_configure`, `modoverride` and the neuromodulation fields —
so the mechanism-specific manipulations (`SynapticMgManipulation`,
`ScaleAcetylcholineUSESynapticManipulation`) are not offered.

`weight` is a factor on each synapse's weight as the circuit defines it, not on its current value,
so overrides never compound: a Connect (weight 1) after a Disconnect (weight 0) restores the
circuit exactly, inhibitory signs included. `synapse_delay_override` replaces the delay outright.

### Neuron sets and timestamps

Neuron sets are restricted to the point-neuron sets (`Brian2SimulationNeuronSetUnion`). Timestamps
blocks are shared with the other simulation configurations and are referenced by the current
injections and the synaptic manipulations.

## Defaults

Every untargeted block — the simulation itself, recordings, stimuli and synaptic manipulations —
falls back to the same default neuron set, `"Default: All Point Neurons"`, which covers every
point neuron in the circuit. The generation task injects it into `neuron_sets` the first time
something needs it.

`Brian2DirectPoissonStimulus` is worth targeting deliberately even so: left untargeted it drives
every point neuron in the circuit, which is rarely what a model calls for. On the FlyWire model
the 20-neuron `sugar` set is the natural target.

A Brian2 configuration also refuses, before generating anything, a circuit that does not have
exactly one point node population, since the runner cannot build a network from it.

## Progress

While simulated time advances, `simulate_brian2.py` prints its progress to stdout in the same form as neurodamus, so a Brian2 job's log reads like a NEURON job's:

```
[t=250.00] Completed 25% ETA: 0:00:31
```

A line is printed at most every two seconds of wall time, and always once the simulation ends. The percentage is of the whole simulation, although the runner advances it with one `network.run` per interval between stimulus and manipulation events. The time remaining leaves out building and compiling the network, which happen before simulated time starts to move. Unlike neurodamus, each update is a line of its own rather than one redrawn with a carriage return, because the job log is read a line at a time.

On FlyWire, staging, building and compiling the network take about a minute before the first of those lines. So on the platform the runner's own messages (loading the neurons and synapses, writing the spikes, registering the result) also go to stdout, as `[INFO] ...` lines, whatever the verbosity.

## Worked example

`examples/obi_one/scientific/tasks/generate_simulations/Brian2/brian2_flywire_simulation.ipynb`
builds a campaign using every block listed above, stages the `FlyWire-v783-Brian2-LIF` circuit
(138,639 neurons, 15,091,983 synapses) from the database, generates the SONATA config, and runs it
through `simulate_brian2.py`'s `sonata-simulation` command.
