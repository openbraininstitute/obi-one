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
the circuit's synapses. The spike stimuli generate a spike file, which the runner replays through
a `SpikeGeneratorGroup` wired with the circuit's *own* connectivity.

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

Every untargeted block — the simulation itself, recordings, stimuli and synaptic manipulations —
falls back to the same default neuron set, `"Default: All Point Neurons"`, which covers every
point neuron in the circuit. The generation task injects it into `neuron_sets` the first time
something needs it.

`Brian2DirectPoissonStimulus` is the one block that cannot usually live with that default: Brian2
instantiates one `PoissonInput` per target neuron, so the block refuses a target above
`MAX_NEURONS` (100). On any real circuit an untargeted Direct Poisson input will exceed that and
has to name a smaller neuron set of its own — on the FlyWire model, the 20-neuron `sugar` set is
the natural choice.

A Brian2 configuration also refuses, before generating anything, a circuit that does not have
exactly one point node population, since the runner cannot build a network from it.

## Worked example

`examples/obi_one/scientific/tasks/generate_simulations/Brian2/brian2_flywire_simulation.ipynb`
builds a campaign using every block listed above, stages the `FlyWire-v783-Brian2-LIF` circuit
(138,639 neurons, 15,091,983 synapses) from the database, generates the SONATA config, and runs it
through `simulate_brian2.py`'s `sonata-simulation` command.
