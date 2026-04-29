# Proposed entitycore `TaskConfigType` / `TaskActivityType` additions for the AIND ephys pipeline

For each notebook 01–11 in this folder we wrap an upstream AllenNeuralDynamics capsule in an `obi.AINDE…ScanConfig` + `AINDE…Task`. To register these with [entitycore](https://github.com/openbraininstitute/entitycore/blob/3bc2a0051c1c1a75e4dc0ad1c9547fc930d163a3/app/db/types.py#L169), each one needs:

- two `TaskConfigType` enum members — one for the campaign-level `TaskConfig` (the serialised `ScanConfig`) and one for the per-coordinate `TaskConfig` (the serialised `SingleConfig`).
- two `TaskActivityType` enum members — one for the scan-generation activity (build the per-coordinate configs) and one for the execution activity (actually run the capsule on a coordinate).

The proposed names follow the existing `<task_slug>__campaign` / `<task_slug>__config` and `<task_slug>__config_generation` / `<task_slug>__execution` convention.

## `TaskConfigType` additions

```python
class TaskConfigType(StrEnum):
    """Task config types."""

    # … existing members …

    aind_ephys_dispatch__campaign = auto()
    aind_ephys_dispatch__config = auto()
    aind_ephys_preprocessing__campaign = auto()
    aind_ephys_preprocessing__config = auto()
    aind_ephys_spikesort_kilosort4__campaign = auto()
    aind_ephys_spikesort_kilosort4__config = auto()
    aind_ephys_postprocessing__campaign = auto()
    aind_ephys_postprocessing__config = auto()
    aind_ephys_curation__campaign = auto()
    aind_ephys_curation__config = auto()
    aind_ephys_visualization__campaign = auto()
    aind_ephys_visualization__config = auto()
    aind_ephys_results_collector__campaign = auto()
    aind_ephys_results_collector__config = auto()
    aind_ephys_processing_qc__campaign = auto()
    aind_ephys_processing_qc__config = auto()
    aind_ephys_qc_collector__campaign = auto()
    aind_ephys_qc_collector__config = auto()
    aind_ecephys_nwb__campaign = auto()
    aind_ecephys_nwb__config = auto()
    aind_units_nwb__campaign = auto()
    aind_units_nwb__config = auto()
```

## `TaskActivityType` additions

```python
class TaskActivityType(StrEnum):
    """Task activity types."""

    # … existing members …

    aind_ephys_dispatch__config_generation = auto()
    aind_ephys_dispatch__execution = auto()
    aind_ephys_preprocessing__config_generation = auto()
    aind_ephys_preprocessing__execution = auto()
    aind_ephys_spikesort_kilosort4__config_generation = auto()
    aind_ephys_spikesort_kilosort4__execution = auto()
    aind_ephys_postprocessing__config_generation = auto()
    aind_ephys_postprocessing__execution = auto()
    aind_ephys_curation__config_generation = auto()
    aind_ephys_curation__execution = auto()
    aind_ephys_visualization__config_generation = auto()
    aind_ephys_visualization__execution = auto()
    aind_ephys_results_collector__config_generation = auto()
    aind_ephys_results_collector__execution = auto()
    aind_ephys_processing_qc__config_generation = auto()
    aind_ephys_processing_qc__execution = auto()
    aind_ephys_qc_collector__config_generation = auto()
    aind_ephys_qc_collector__execution = auto()
    aind_ecephys_nwb__config_generation = auto()
    aind_ecephys_nwb__execution = auto()
    aind_units_nwb__config_generation = auto()
    aind_units_nwb__execution = auto()
```

## Mapping to the OBI ScanConfigs / Tasks

| # | Notebook | Slug | OBI ScanConfig | OBI Task | Upstream capsule |
|---|---|---|---|---|---|
| 01 | `01_aind_ephys_dispatch.ipynb` | `aind_ephys_dispatch` | `AINDEPhysDispatchScanConfig` | `AINDEPhysDispatchTask` | [aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch) |
| 02 | `02_aind_ephys_preprocessing.ipynb` | `aind_ephys_preprocessing` | `AINDEPhysPreprocessingScanConfig` | `AINDEPhysPreprocessingTask` | [aind-ephys-preprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing) |
| 03 | `03_aind_ephys_spikesort_kilosort4.ipynb` | `aind_ephys_spikesort_kilosort4` | `AINDEPhysSpikesortKilosort4ScanConfig` | `AINDEPhysSpikesortKilosort4Task` | [aind-ephys-spikesort-kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4) |
| 04 | `04_aind_ephys_postprocessing.ipynb` | `aind_ephys_postprocessing` | `AINDEPhysPostprocessingScanConfig` | `AINDEPhysPostprocessingTask` | [aind-ephys-postprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing) |
| 05 | `05_aind_ephys_curation.ipynb` | `aind_ephys_curation` | `AINDEPhysCurationScanConfig` | `AINDEPhysCurationTask` | [aind-ephys-curation](https://github.com/AllenNeuralDynamics/aind-ephys-curation) |
| 06 | `06_aind_ephys_visualization.ipynb` | `aind_ephys_visualization` | `AINDEPhysVisualizationScanConfig` | `AINDEPhysVisualizationTask` | [aind-ephys-visualization](https://github.com/AllenNeuralDynamics/aind-ephys-visualization) |
| 07 | `07_aind_ephys_results_collector.ipynb` | `aind_ephys_results_collector` | `AINDEPhysResultsCollectorScanConfig` | `AINDEPhysResultsCollectorTask` | [aind-ephys-results-collector](https://github.com/AllenNeuralDynamics/aind-ephys-results-collector) |
| 08 | `08_aind_ephys_processing_qc.ipynb` | `aind_ephys_processing_qc` | `AINDEPhysProcessingQCScanConfig` | `AINDEPhysProcessingQCTask` | [aind-ephys-processing-qc](https://github.com/AllenNeuralDynamics/aind-ephys-processing-qc) |
| 09 | `09_aind_ephys_qc_collector.ipynb` | `aind_ephys_qc_collector` | `AINDEPhysQCCollectorScanConfig` | `AINDEPhysQCCollectorTask` | [aind-ephys-qc-collector](https://github.com/AllenNeuralDynamics/aind-ephys-qc-collector) |
| 10 | `10_aind_ecephys_nwb.ipynb` | `aind_ecephys_nwb` | `AINDEcephysNWBScanConfig` | `AINDEcephysNWBTask` | [aind-ecephys-nwb](https://github.com/AllenNeuralDynamics/aind-ecephys-nwb) |
| 11 | `11_aind_units_nwb.ipynb` | `aind_units_nwb` | `AINDUnitsNWBScanConfig` | `AINDUnitsNWBTask` | [aind-units-nwb](https://github.com/AllenNeuralDynamics/aind-units-nwb) |

Note on naming: the upstream repo for notebook 10 is `aind-ecephys-nwb` (not `aind-ephys-nwb`), so the slug uses `aind_ecephys_nwb` — keeping it aligned with the GitHub repo / class name (`AINDEcephysNWBTask`). Every other slug uses the `aind_ephys_` prefix.

## OBI-side wiring once these are merged

Each `ScanConfig` already has the two `ClassVar` hooks ready for these enums (currently set to `None`):

```python
class AINDEPhysDispatchScanConfig(ScanConfig):
    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None
```

Once the new enum members land in entitycore, replace the `None`s with the matching `__campaign` / `__config_generation` members (and the per-coordinate `SingleConfig` will pick up `__config` / `__execution` via the ScanConfig wiring). All 11 ScanConfigs need the same one-line update; the existing `create_campaign_entity_with_config` / `create_single_entity_with_config` no-ops can then call into `db_sdk.register_task_config_with_asset(...)` like the simulation/extraction tasks already do.
