---
tags:
  - build-ion-channel-model
---

# Ion Channel Model Fitting

`IonChannelFittingScanConfig` fits a Hodgkin-Huxley ion channel model to one or more ion channel recordings with `ion-channel-builder`, writes it out as a NEURON mod file and registers it as an `IonChannelModel`.

## Configuration

- **Recordings** (`initialize.recordings`): every selected recording is fitted jointly into one model, not one model each.
- **Model properties** (`initialize.model_properties`): the ion channel name, temperature, species, strain and brain region the model is registered with. Each one left unset comes from the recordings:
    - the ion channel name (the `SUFFIX` of the mod file, a valid NEURON identifier) from the recordings' channel, so `Kv6.2` gives `Kv6_2`;
    - the temperature and the species from the recordings;
    - the strain from the recordings of the model's species, none if there are none;
    - the brain region is the deepest region containing every recording's region.

    A set property wins even when the recordings agree. When the recordings differ in the channel, temperature, species or strain, that property has to be set; generation rejects the config before registering anything.
- **Model** (`model_type`): one equation per gating variable (m∞, τₘ, h∞, τₕ) and the exponents of m and h in g = ḡ·mᵖ·hᵠ. The exponents can be swept; each value pair becomes its own config and its own fitted model.

## Entities

Generation registers an `ion_channel_modeling__campaign` TaskConfig and one `ion_channel_modeling__config` TaskConfig per coordinate, linked by an `ion_channel_modeling__config_generation` TaskActivity. Each fit runs as an `ion_channel_modeling__execution` TaskActivity that uses its config and generates the `IonChannelModel`. All of them list the recordings as inputs.

The model links to the recordings' subject when they all share one with the model's species and strain. Otherwise it links to the `Generic <species>` or `Generic <species>/<strain>` subject, and registers one in the project when there is none.

## Running

On the platform the fit runs in Bluenaas, which takes the id of a single config. The task is also registered with the launch system (`ion_channel_fitting` dependencies in `launch_scripts/launch_task_for_single_config_asset/dependencies/`), and the example notebook in `examples/obi_one/scientific/tasks/ion_channel_modeling/` runs a single fit locally.

Each fit compiles its mechanism into its own coordinate folder and plots it in a fresh Python interpreter, since NEURON loads a mechanism name only once per process and every fit of a sweep uses the same name.
