# K_extracellular — AIND Ephys Pipeline Demo

End-to-end walk-through of the [AIND ephys pipeline](https://github.com/AllenNeuralDynamics) (job dispatch → preprocessing → spike sorting → postprocessing → curation → visualization → results collection → QC → NWB export) running locally against a tiny synthetic SpikeInterface recording.

Each notebook builds an `obi.AINDE...ScanConfig`, expands it via `GridScanGenerationTask`, and runs the corresponding `AINDE...Task` for each coordinate. The task itself clones the upstream AllenNeuralDynamics capsule into `/tmp/`, seeds its `data/` from the previous stage's `obi-output/<NN>_…/grid_scan/0/` directory, runs the capsule's `code/run_capsule.py`, and writes results into the single config's `coordinate_output_root`. Every stage's output lives under `obi-output/` (outside the repo).

## Run order

Run the notebooks in numerical order (00 → 11). Each stage reads `obi-output/<NN-1>_…/grid_scan/0/` (or sibling) directly — no intermediate copying.

## Notebooks

| # | Notebook | What it does | Reads from | Writes to |
|---|---|---|---|---|
| 00 | `00_generate_toy_recording.ipynb` | Installs `spikeinterface` and generates a 10 s, 70-channel, 10-unit ground-truth `BinaryFolderRecording`. | — | `obi-output/00_toy_example_recording/` |
| 01 | `01_aind_ephys_dispatch.ipynb` | Runs [aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch). Builds `obi.AINDEPhysDispatchScanConfig` + `GridScanGenerationTask`; the task invokes the dispatch CLI with `--input spikeinterface --spikeinterface-info '{...}'`. Produces a `job_0.json` describing the recording. | `obi-output/00_toy_example_recording/` | `obi-output/01_aind_ephys_dispatch/grid_scan/0/job_0.json` |
| 02 | `02_aind_ephys_preprocessing.ipynb` | Runs [aind-ephys-preprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing) on a 1-second clip (`t_start=0`, `t_stop=1`). Lowers `min_preprocessing_duration` to 0.5 s and disables motion correction. | `obi-output/01_aind_ephys_dispatch/grid_scan/0/` | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/preprocessed_<name>/`, `binary_<name>.json`, … |
| 03 | `03_aind_ephys_spikesort_kilosort4.ipynb` | Re-runs preprocessing at 8 s (KS4 needs > 1 s for whitening), then runs [aind-ephys-spikesort-kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4). Tunes `whitening_range`, `nskip`, `nearest_chans`, `nearest_templates`; pins `torch_device="cpu"`; disables drift correction. | `obi-output/01_aind_ephys_dispatch/grid_scan/0/` | `obi-output/03_aind_ephys_spikesort_kilosort4/{preprocessing,sorting}/0/` (~14 KS4 units) |
| 04 | `04_aind_ephys_postprocessing.ipynb` | Runs [aind-ephys-postprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing). | `obi-output/03_aind_ephys_spikesort_kilosort4/preprocessing/0/`, `…/sorting/0/` | `obi-output/04_aind_ephys_postprocessing/grid_scan/0/postprocessed_<name>.zarr` (10 deduplicated units, 26 quality metrics) |
| 05 | `05_aind_ephys_curation.ipynb` | Runs [aind-ephys-curation](https://github.com/AllenNeuralDynamics/aind-ephys-curation). Default QC query plus the HuggingFace `SpikeInterface/UnitRefine_*` noise-neural & SUA/MUA classifiers. | `obi-output/04_aind_ephys_postprocessing/grid_scan/0/` | `obi-output/05_aind_ephys_curation/grid_scan/0/qc_<name>.npy`, `unit_classifier_<name>.csv` |
| 06 | `06_aind_ephys_visualization.ipynb` | Runs [aind-ephys-visualization](https://github.com/AllenNeuralDynamics/aind-ephys-visualization). Without a `KACHERY_API_KEY`, only emits local PNGs (drift map, raw + preprocessed traces). | `obi-output/01_aind_ephys_dispatch/grid_scan/0/`, `obi-output/03_…/preprocessing/0/`, `obi-output/04_…/grid_scan/0/`, `obi-output/05_…/grid_scan/0/` | `obi-output/06_aind_ephys_visualization/grid_scan/0/visualization_<name>/*.png` |
| 07 | `07_aind_ephys_results_collector.ipynb` | Runs [aind-ephys-results-collector](https://github.com/AllenNeuralDynamics/aind-ephys-results-collector). Aggregates the previous stages into `{preprocessed,spikesorted,postprocessed,curated,visualization}/` plus the AIND-data-schema `processing.json` / `data_description.json`. The task synthesises a minimal `ecephys_<session>/` folder so the capsule's `assert len(ecephys_sessions) == 1` passes. | `obi-output/01_…`, `obi-output/03_…/preprocessing/0/`, `obi-output/03_…/sorting/0/`, `obi-output/04_…`, `obi-output/05_…`, `obi-output/06_…` | `obi-output/07_aind_ephys_results_collector/grid_scan/0/{preprocessed,spikesorted,postprocessed,curated,visualization}/`, `processing.json`, `data_description.json` |
| 08 | `08_aind_ephys_processing_qc.ipynb` | Runs [aind-ephys-processing-qc](https://github.com/AllenNeuralDynamics/aind-ephys-processing-qc) on the collected layout. | `obi-output/07_…`, `obi-output/01_…/grid_scan/0/` | `obi-output/08_aind_ephys_processing_qc/grid_scan/0/quality_control_<name>.json` (5 metrics: Raw data {traces, PSD, RMS}, Processing {Unit yield, Firing rate}) + 5 PNGs |
| 09 | `09_aind_ephys_qc_collector.ipynb` | Runs [aind-ephys-qc-collector](https://github.com/AllenNeuralDynamics/aind-ephys-qc-collector). Aggregates per-recording QC into a single `quality_control.json` with `default_grouping=['probe', 'stage']` and a flat `quality_control/<probe>/` figure tree. | `obi-output/08_…/grid_scan/0/` | `obi-output/09_aind_ephys_qc_collector/grid_scan/0/quality_control.json`, `quality_control/<probe>/*.png` |
| 10 | `10_aind_ecephys_nwb.ipynb` | Runs [aind-ecephys-nwb](https://github.com/AllenNeuralDynamics/aind-ecephys-nwb). Writes one HDF5 NWB per (block, recording) with the raw `ElectricalSeries`. We `--write-raw --skip-lfp`. | `obi-output/01_…/grid_scan/0/` | `obi-output/10_aind_ecephys_nwb/grid_scan/0/<session>_block0_recording1.nwb` (~76 MB) |
| 11 | `11_aind_units_nwb.ipynb` | Runs [aind-units-nwb](https://github.com/AllenNeuralDynamics/aind-units-nwb). Appends the curated sorting + waveforms to the base NWB. The resulting `units` table has UUIDs, KS unit ids, amplitude, depth, every quality + template metric, and the curation `decoder_label` / `default_qc`. | `obi-output/10_…/grid_scan/0/`, `obi-output/07_…/grid_scan/0/{postprocessed,curated,spikesorted}/`, `obi-output/01_…/grid_scan/0/` | `obi-output/11_aind_units_nwb/grid_scan/0/<session>_block0_recording1.nwb` (~78 MB) with `units` table |

## In-place patches applied to upstream capsules

Several capsules were authored against an older spikeinterface (≤ 0.103) or older neuroconv. The OBI tasks patch the cloned `/tmp/aind-*/code/` files in place on first run so the capsules work against current `spikeinterface==0.104.x` and current `neuroconv`. The original GitHub repos are untouched.

| # | Capsule | Patches applied by the task | Why |
|---|---|---|---|
| 04 | aind-ephys-postprocessing | `qm_params=quality_metrics_params` → `metric_params=quality_metrics_params` in `code/run_capsule.py` | Newer spikeinterface renamed the kwarg of `SortingAnalyzer.compute("quality_metrics", …)`. |
| 04 | aind-ephys-postprocessing (config-side, not a code patch but a params-side workaround in `params_dict()`) | `template_metrics.sparsity` is **not** emitted; `quality_metrics_names` swaps `l_ratio` / `isolation_distance` → `mahalanobis`; per-metric configs filtered to only the still-valid metric names. | Newer `ComputeTemplateMetrics` rejects `sparsity`; `l_ratio` / `isolation_distance` were merged into `mahalanobis`; deprecated `nn_isolation` / `nn_noise_overlap` blocks would fail validation. |
| 05 | aind-ephys-curation | `scikit-learn==1.5.2` pinned in the install cell. | The HuggingFace `SpikeInterface/UnitRefine_*` skops models were trained against sklearn 1.5; loading them under 1.8 fails with `'SimpleImputer' object has no attribute '_fill_dtype'`. |
| 08 | aind-ephys-processing-qc | In `code/qc_utils.py`: `spre.bandpass_filter(recording, freq_min=0.1, freq_max=freq_lfp)` → `…, ignore_low_freq_error=True)`. | Newer spikeinterface guards against sub-Hz bandpass cutoffs. |
| 08 | aind-ephys-processing-qc | In `code/qc_utils.py`: `template_metrics['half_width']` → `template_metrics['trough_half_width']`. | Newer spikeinterface renamed the column. |
| 10 | aind-ecephys-nwb | In `code/run_capsule.py`: `add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`. | Renamed in newer neuroconv. |
| 11 | aind-units-nwb | In `code/utils.py`: `add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`; `add_units_table_to_nwbfile` → `_add_units_table_to_nwbfile` (now private). Both rewrites are idempotent so re-runs don't compound underscores. | Renamed / privatised in newer neuroconv. |

## Where `job_0.json` is used

`obi-output/01_aind_ephys_dispatch/grid_scan/0/job_0.json` is the dispatcher's serialised `recording_dict` — a SpikeInterface JSON pointing at the toy recording with paths relative to `data/`. It encodes which raw data each downstream stage should load.

Notebooks that consume it directly:

- **02** — preprocessing seeds it into the capsule's `data/`.
- **03** — re-runs preprocessing at 8 s, reusing the same `job_0.json`.
- **06** — visualization needs it to load the raw recording for trace snippets.
- **07** — results-collector copies it into the aggregated layout.
- **08** — processing-qc loads the raw recording from it for raw-data metrics.
- **10** — `aind-ecephys-nwb` reads `recording_dict` to write the raw `ElectricalSeries`.
- **11** — `aind-units-nwb` reads `recording_dict` to look up the recording when writing waveforms / electrodes.

Notebooks that don't touch `job_0.json` directly: 00, 04 (postprocessing — uses preprocessed binary), 05 (curation — uses postprocessed zarr), 09 (qc-collector — operates on QC JSON files only).

## Output layout

Everything each stage produces lives under `obi-output/` (outside the repo, per OBI convention; see `CLAUDE.md`):

```
obi-output/
├── 00_toy_example_recording/
├── 01_aind_ephys_dispatch/grid_scan/0/
├── 02_aind_ephys_preprocessing/grid_scan/0/
├── 03_aind_ephys_spikesort_kilosort4/{preprocessing,sorting}/0/
├── 04_aind_ephys_postprocessing/grid_scan/0/
├── 05_aind_ephys_curation/grid_scan/0/
├── 06_aind_ephys_visualization/grid_scan/0/
├── 07_aind_ephys_results_collector/grid_scan/0/
├── 08_aind_ephys_processing_qc/grid_scan/0/
├── 09_aind_ephys_qc_collector/grid_scan/0/
├── 10_aind_ecephys_nwb/grid_scan/0/
└── 11_aind_units_nwb/grid_scan/0/
```

Every grid scan uses `coordinate_directory_option="ZERO_INDEX"` so coord 0 is always at `<output_root>/0/`. With sweep dimensions you'd see `1/`, `2/`, … alongside it.

## Notes on running locally

- All capsules are cloned to `/tmp/aind-*` on first run; subsequent runs reuse the clone (and its applied patches).
- KS4 runs on CPU here (no CUDA). For the toy data this takes ~10 s.
- The HuggingFace classifiers in 05 download a few MB on first run; subsequent runs are cached.
- No `KACHERY_API_KEY` is set, so 06 only writes local PNGs.
