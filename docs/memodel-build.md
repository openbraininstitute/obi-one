---
tags:
  - build-single-neuron-model
---

# ME-model Build

`MEModelBuildScanConfig` combines one cell morphology and one e-model into an `MEModel`, then calibrates and validates it with bluecellulab (optional extra: `pip install 'obi-one[bluecellulab]'`).

## Configuration

- **Info** (`info`): the campaign name and description become the ME-model's name and description.
- **Morphology** (`initialize.morphology`) and **E-model** (`initialize.emodel`): one of each. They are single entities, not scan dimensions, so a campaign builds one ME-model.

The ME-model gets its species, strain and brain region from the morphology, its m-types from the morphology and its e-types from the e-model.

## Entities

Generation registers a `memodel_build__campaign` TaskConfig and one `memodel_build__config` TaskConfig, linked by a `memodel_build__config_generation` TaskActivity. The build runs as a `memodel_build__execution` TaskActivity. Both TaskConfigs list the morphology and the e-model as inputs; the generation activity uses the campaign and the execution activity uses the config.

The task:

1. resolves the morphology and e-model once, downloads their hoc, morphology and mechanisms, and compiles the mechanisms;
2. calibrates holding current, rheobase and input resistance (starting from a holding current of 0 nA and a threshold current of 0.1 nA);
3. registers the `MEModel` with those currents and `validation_status=created`, its creator `Contribution`, its m-type and e-type classifications, and an `MEModelCalibrationResult`, then writes the ME-model to the activity's `generated` so it can be simulated while validation runs;
4. runs the bluecellulab validations with the calibrated currents, registers one `ValidationResult` per validation, then sets `validation_status=done`.

`done` means the validations ran; each `ValidationResult` says whether its test passed. Failures before registration leave no ME-model. When a step after registration fails, the ME-model stays with `validation_status=error` and the activity ends in error. A calibration registered before a failed validation stays.

## Running

On the platform the build runs in Bluenaas, which takes the id of the single config. The task is also registered with the launch system, and the example notebook in `examples/obi_one/scientific/tasks/memodel_build/` runs a build locally.

Calibration and validation run in fresh Python processes, since NEURON loads mechanisms only once per process.
