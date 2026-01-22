---
tags:
  - circuit-simulation
---

# Small Circuit Simulations

Small circuit simulations in OBI-one simulate networks of interconnected neurons using SONATA circuit format. A "small circuit" is defined as a circuit containing up to 20 biophysical neurons.

## Overview

Circuit simulations model networks of neurons with their synaptic connections, allowing you to study network dynamics, connectivity patterns, and emergent behaviors. Unlike single cell simulations, circuit simulations include:

- **Multiple neurons**: Networks of interconnected biophysical neurons
- **Synaptic connections**: Edges between neurons with synaptic mechanisms
- **Neuron sets**: Flexible selection of which neurons to simulate
- **Synaptic manipulations**: Ability to modify synaptic properties during simulation

## Key Components

### CircuitSimulationSingleConfig

The `CircuitSimulationSingleConfig` class (located in `obi_one/scientific/tasks/generate_simulation_configs.py`) is used to configure circuit simulations. It includes:

- **Circuit**: A SONATA circuit to simulate (can be `Circuit` or `CircuitFromID`)
- **Neuron Sets**: Dictionary of neuron sets defining which neurons to include
- **Node Set**: Reference to the specific neuron set to simulate (must be biophysical)
- **Synaptic Manipulations**: Optional modifications to synaptic properties
- **Simulation Parameters**: Duration, timestep, initial voltage, extracellular calcium
- **Stimuli**: Various stimulus types that can be applied to the network
- **Recordings**: Voltage and other electrophysiological recordings

### Circuit Class

The `Circuit` class (`obi_one/scientific/library/circuit.py`) represents a SONATA circuit:

- **Path**: Points to a SONATA circuit configuration file
- **Node Populations**: Groups of neurons (biophysical, point neurons, virtual)
- **Edge Populations**: Synaptic connections between populations
- **Node Sets**: Predefined or custom sets of neurons
- **Connectivity Matrix**: Optional connectivity matrix for analysis

### GenerateSimulationTask

The `GenerateSimulationTask` class (`obi_one/scientific/tasks/generate_simulation_task.py`) handles circuit simulation configuration:

1. **Resolves the circuit**: Loads circuit from path or entity database
2. **Initializes SONATA config**: Sets up simulation parameters (duration, timestep, conditions)
3. **Configures synaptic mechanisms**: Adds ProbAMPANMDA_EMS and ProbGABAAB_EMS mechanisms
4. **Resolves neuron sets**: Processes neuron set definitions and writes node_sets.json
5. **Adds inputs**: Configures stimuli (current clamp, spike trains, etc.)
6. **Adds reports**: Configures recordings (voltage traces, spikes)
7. **Adds manipulations**: Applies synaptic manipulations if specified
8. **Writes simulation config**: Generates simulation_config.json in SONATA format

### Simulation Execution

Circuit simulations use the same execution backend as single cell simulations (`obi_one/scientific/library/simulation_execution.py`):

- **BlueCelluLab Backend**: Primary simulation backend using NEURON
- **MPI Support**: Distributed execution across multiple processes
- **Cell Distribution**: Automatically distributes neurons across MPI ranks
- **Result Gathering**: Collects voltage traces and spikes from all ranks

## Circuit Scale Classification

Circuits are automatically classified by size (`obi_one/scientific/tasks/circuit_extraction.py`):

- **Single**: 1 neuron
- **Pair**: 2 neurons  
- **Small**: 3-20 neurons (`_MAX_SMALL_MICROCIRCUIT_SIZE = 20`)
- **Microcircuit**: >20 neurons

Small circuits (≤20 neurons) are optimized for rapid testing and development, while larger circuits require more computational resources.

## Configuration Structure

A typical circuit simulation configuration includes:

```python
from obi_one import CircuitSimulationSingleConfig, CircuitFromID, AllNeurons

config = CircuitSimulationSingleConfig(
    initialize=CircuitSimulationSingleConfig.Initialize(
        circuit=CircuitFromID(id="..."),
        node_set=NeuronSetReference(block_dict_name="neuron_sets", block_name="All Biophys"),
        simulation_length=3000.0,  # ms
        v_init=-80.0,  # mV
        extracellular_calcium_concentration=1.1,  # mM
        random_seed=1
    ),
    neuron_sets={
        "All Biophys": AllNeurons(sample_percentage=100.0, sample_seed=1)
    },
    stimuli={...},
    recordings={...},
    synaptic_manipulations={...},
    timestamps={...}
)
```

## Key Parameters

### Initialize Block

- **circuit**: Circuit to simulate (can be `Circuit` or `CircuitFromID`)
- **node_set**: Neuron set reference specifying which neurons to simulate (must be biophysical)
- **simulation_length**: Duration in milliseconds (default: 1000.0 ms)
- **v_init**: Initial membrane potential in millivolts (default: -80.0 mV)
- **extracellular_calcium_concentration**: Extracellular calcium concentration in mM (default: 1.1 mM)
- **random_seed**: Random seed for reproducibility
- **timestep**: Simulation time step in ms (default: 0.025 ms)
- **spike_location**: Location for spike detection - "soma" or "AIS" (default: "soma")

### Neuron Sets

Neuron sets define which neurons participate in the simulation:

- **AllNeurons**: All biophysical neurons in the circuit
- **IDNeuronSet**: Specific neurons by ID
- **PropertyNeuronSet**: Neurons matching specific properties
- **PredefinedNeuronSet**: Predefined sets from the circuit
- **CombinedNeuronSet**: Logical combinations of other sets

The `initialize.node_set` must reference a biophysical neuron set.

### Synaptic Mechanisms

Circuit simulations automatically include synaptic mechanisms:

- **ProbAMPANMDA_EMS**: Excitatory AMPA/NMDA synapses with single vesicle minis
- **ProbGABAAB_EMS**: Inhibitory GABA-A/B synapses with single vesicle minis

These mechanisms support:
- Initial depletion state
- Single vesicle mini events
- Probabilistic release

### Synaptic Manipulations

Optional modifications to synaptic properties:

- **SynapticMgManipulation**: Modify magnesium block of NMDA receptors
- **ScaleAcetylcholineUSESynapticManipulation**: Scale acetylcholine effects

Manipulations are applied as `connection_overrides` in the SONATA config.

### Stimuli

Various stimulus types for network activation:

- **Current clamp stimuli**: Constant, linear, sinusoidal, etc.
- **Spike-based stimuli**: Poisson, synchronous, sinusoidal Poisson
- **Targeted stimuli**: Can target specific neuron sets

### Recordings

Recordings capture network activity:

- **SomaVoltageRecording**: Voltage traces from soma
- **TimeWindowSomaVoltageRecording**: Voltage within specific time windows
- **Spike detection**: Automatic spike detection and recording

## Running Simulations

### Using GenerateSimulationTask

```python
from obi_one import GenerateSimulationTask

task = GenerateSimulationTask(config=config)
task.execute(db_client=db_client, entity_cache=False)
```

The task generates:
- `simulation_config.json`: SONATA simulation configuration
- `node_sets.json`: Custom node set definitions
- Circuit staging: Downloads and stages circuit files if using `CircuitFromID`

### Direct Execution

After generating the simulation config:

```python
from obi_one.scientific.library.simulation_execution import run

run(
    simulation_config="path/to/simulation_config.json",
    simulator="bluecellulab",
    save_nwb=True
)
```

## Output

Simulation outputs include:

- **Voltage traces**: Time-series voltage data for all recorded neurons
- **Spike times**: Detected action potentials for all neurons
- **NWB files**: Neurodata Without Borders format for standardized data storage
- **Reports**: Various analysis reports generated by BlueCelluLab
- **Spike files**: HDF5 files with spike times by population

## Differences from Single Cell Simulations

| Feature | Single Cell (MEModel) | Circuit Simulation |
|---------|----------------------|---------------------|
| Neurons | 1 | Multiple (network) |
| Synapses | Optional (MEModelWithSynapses) | Always present |
| Neuron Sets | Not applicable | Required |
| Synaptic Mechanisms | Optional | Always enabled |
| Connectivity | None | Full network connectivity |
| Stimuli | Direct to cell | Can target neuron sets |
| Output | Single cell traces | Network-wide activity |

## Examples

See the examples directory for notebook examples:

- `examples/E_run_small_microcircuit/` - Small circuit simulation examples
- `examples/C_forms/circuit_simulation/` - Circuit simulation configuration examples
