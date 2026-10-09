---
tags:
  - build-ion-channel-model
---

# Ion Channel Model Fitting

`IonChannelFittingScanConfig` fits a Hodgkin-Huxley ion channel model to one or more ion channel recordings with `ion-channel-builder`, writes it out as a NEURON mod file and registers it as an `IonChannelModel`.

## Configuration

- **Recordings** (`initialize.recordings`): every selected recording is fitted jointly into one model, not one model each. They must share a temperature, because the model records a single one; generation rejects a mixed set before registering anything.
- **Ion channel name** (`initialize.ion_channel_name`): the `SUFFIX` of the mod file, so it has to be a valid NEURON identifier.
- **Model** (`model_type`): one equation per gating variable (m∞, τₘ, h∞, τₕ) and the exponents of m and h in g = ḡ·mᵖ·hᵠ. The exponents can be swept; each value pair becomes its own config and its own fitted model.

## Entities

Generation registers an `ion_channel_modeling__campaign` TaskConfig and one `ion_channel_modeling__config` TaskConfig per coordinate, linked by an `ion_channel_modeling__config_generation` TaskActivity. Each fit runs as an `ion_channel_modeling__execution` TaskActivity that uses its config and generates the `IonChannelModel`. All of them list the recordings as inputs.

## Running

On the platform the fit runs in Bluenaas, which takes the id of a single config. The task is also registered with the launch system (`ion_channel_fitting` dependencies in `launch_scripts/launch_task_for_single_config_asset/dependencies/`), and the example notebook in `examples/obi_one/scientific/tasks/ion_channel_modeling/` runs a single fit locally.

Each fit compiles its mechanism into its own coordinate folder and plots it in a fresh Python interpreter, since NEURON loads a mechanism name only once per process and every fit of a sweep uses the same name.
