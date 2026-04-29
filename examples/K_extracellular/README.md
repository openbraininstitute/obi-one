# K_extracellular — AIND Ephys Pipeline Demo

End-to-end walk-through of the [AIND ephys pipeline](https://github.com/AllenNeuralDynamics) (job dispatch → preprocessing → spike sorting → postprocessing → curation → visualization → results collection → QC → NWB export) running locally against a tiny synthetic SpikeInterface recording.

Each notebook builds an `obi.AINDE…ScanConfig`, expands it via `GridScanGenerationTask`, and runs the corresponding `AINDE…Task` for each coordinate. The task itself clones the upstream AllenNeuralDynamics capsule into `/tmp/`, seeds its `data/` from the previous stage's `obi-output/<NN>_…/grid_scan/0/` directory, runs the capsule's `code/run_capsule.py`, and writes results into the single config's `coordinate_output_root`. Every stage's output lives under `obi-output/` (outside the repo).

Every grid scan uses `coordinate_directory_option="ZERO_INDEX"` so coord 0 is always at `<output_root>/0/`. With sweep dimensions you'd see `1/`, `2/`, … alongside it.

## Run order

Run the notebooks in numerical order (00 → 11). Each stage reads `obi-output/<NN-1>_…/grid_scan/0/` (or sibling) directly — no intermediate copying.

## Notebooks

| # | Notebook | What it does | Reads from | Writes to |
|---|---|---|---|---|
| 00 | `00_generate_toy_recording.ipynb` | Installs `spikeinterface` and generates a 10 s, 70-channel, 10-unit ground-truth `BinaryFolderRecording`. | — | `obi-output/00_toy_example_recording/` |
| 01 | `01_aind_ephys_dispatch.ipynb` | Runs [aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch). Builds `obi.AINDEPhysDispatchScanConfig` + `GridScanGenerationTask`; the task invokes the dispatch CLI with `--input spikeinterface --spikeinterface-info '{...}'`. | `obi-output/00_toy_example_recording/` | `obi-output/01_aind_ephys_dispatch/grid_scan/0/job_0.json` |
| 02 | `02_aind_ephys_preprocessing.ipynb` | Runs [aind-ephys-preprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing) on a 9-second clip (`t_start=0`, `t_stop=9`). Applies CMR denoising + highpass filter; disables motion correction. | `obi-output/01_aind_ephys_dispatch/grid_scan/0/` | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/preprocessed_<name>/`, `binary_<name>.json`, … |
| 03 | `03_aind_ephys_spikesort_kilosort4.ipynb` | Runs [aind-ephys-spikesort-kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4) directly on notebook 02's 9-second preprocessed binary (no extra preprocessing here). Tunes `whitening_range`, `nskip`, `nearest_chans`, `nearest_templates`; pins `torch_device="cpu"`; disables drift correction. | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/` | `obi-output/03_aind_ephys_spikesort_kilosort4/grid_scan/0/spikesorted_<name>/` (~14 KS4 units) |
| 04 | `04_aind_ephys_postprocessing.ipynb` | Runs [aind-ephys-postprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing). | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/`, `obi-output/03_…/grid_scan/0/` | `obi-output/04_aind_ephys_postprocessing/grid_scan/0/postprocessed_<name>.zarr` (10 deduplicated units, 26 quality metrics) |
| 05 | `05_aind_ephys_curation.ipynb` | Runs [aind-ephys-curation](https://github.com/AllenNeuralDynamics/aind-ephys-curation). Default QC query plus the HuggingFace `SpikeInterface/UnitRefine_*` noise-neural & SUA/MUA classifiers. | `obi-output/04_aind_ephys_postprocessing/grid_scan/0/` | `obi-output/05_aind_ephys_curation/grid_scan/0/qc_<name>.npy`, `unit_classifier_<name>.csv` |
| 06 | `06_aind_ephys_visualization.ipynb` | Runs [aind-ephys-visualization](https://github.com/AllenNeuralDynamics/aind-ephys-visualization). Without a `KACHERY_API_KEY`, only emits local PNGs (drift map, raw + preprocessed traces). | `obi-output/01_…/grid_scan/0/`, `obi-output/02_…/grid_scan/0/`, `obi-output/04_…/grid_scan/0/`, `obi-output/05_…/grid_scan/0/` | `obi-output/06_aind_ephys_visualization/grid_scan/0/visualization_<name>/*.png` |
| 07 | `07_aind_ephys_results_collector.ipynb` | Runs [aind-ephys-results-collector](https://github.com/AllenNeuralDynamics/aind-ephys-results-collector). Aggregates the previous stages into `{preprocessed,spikesorted,postprocessed,curated,visualization}/` plus the AIND-data-schema `processing.json` / `data_description.json`. The task synthesises a minimal `ecephys_<session>/` folder so the capsule's `assert len(ecephys_sessions) == 1` passes. | `obi-output/01_…`, `obi-output/02_…`, `obi-output/03_…`, `obi-output/04_…`, `obi-output/05_…`, `obi-output/06_…` | `obi-output/07_aind_ephys_results_collector/grid_scan/0/{preprocessed,spikesorted,postprocessed,curated,visualization}/` + `processing.json` + `data_description.json` + `subject.json` |
| 08 | `08_aind_ephys_processing_qc.ipynb` | Runs [aind-ephys-processing-qc](https://github.com/AllenNeuralDynamics/aind-ephys-processing-qc) on the collected layout. | `obi-output/07_…/grid_scan/0/`, `obi-output/01_…/grid_scan/0/` | `obi-output/08_aind_ephys_processing_qc/grid_scan/0/quality_control_<name>.json` (5 metrics) + 5 PNGs |
| 09 | `09_aind_ephys_qc_collector.ipynb` | Runs [aind-ephys-qc-collector](https://github.com/AllenNeuralDynamics/aind-ephys-qc-collector). Aggregates per-recording QC into a single `quality_control.json` plus a flat `quality_control/<probe>/` figure tree. | `obi-output/08_…/grid_scan/0/` | `obi-output/09_aind_ephys_qc_collector/grid_scan/0/quality_control.json`, `quality_control/<probe>/*.png` |
| 10 | `10_aind_ecephys_nwb.ipynb` | Runs [aind-ecephys-nwb](https://github.com/AllenNeuralDynamics/aind-ecephys-nwb). Writes one HDF5 NWB per (block, recording) with the raw `ElectricalSeries`. Flags: `--write-raw --skip-lfp`. | `obi-output/01_…/grid_scan/0/` | `obi-output/10_aind_ecephys_nwb/grid_scan/0/<session>_<block>_<recording>.nwb` (~76 MB) |
| 11 | `11_aind_units_nwb.ipynb` | Runs [aind-units-nwb](https://github.com/AllenNeuralDynamics/aind-units-nwb). Appends the curated sorting + waveforms to the base NWB. | `obi-output/10_…/grid_scan/0/`, `obi-output/07_…/grid_scan/0/{postprocessed,curated,spikesorted}/`, `obi-output/01_…/grid_scan/0/` | `obi-output/11_aind_units_nwb/grid_scan/0/<session>_<block>_<recording>.nwb` (~79 MB, with `units` table) |

## What each output actually contains

The OBI framework always writes two metadata files alongside whatever the wrapped capsule produces:

- **`obi_one_scan.json`** at `<output_root>/` — the serialised `ScanConfig` (every parameter the user set).
- **`obi_one_coordinate.json`** at `<output_root>/<idx>/` — the serialised `SingleConfig` for that one coordinate (concrete values for sweep dims).

Everything else listed below is what the upstream capsule itself produces.

### 00 — Toy recording (`obi-output/00_toy_example_recording/`)

A SpikeInterface `BinaryFolderRecording` written by `recording.save(folder=…)`:

- `binary.json` — `BinaryFolderRecording` reader recipe (sample rate, dtype, segment offsets).
- `traces_cached_seg0.raw` — the raw float32 voltage samples (70 ch × 300 000 samples = 80.1 MiB).
- `probe.json` — ProbeInterface description (electrode locations, contact vector, shank groups).
- `provenance.pkl` — pickle of how this recording was constructed (the `generate_ground_truth_recording` call).
- `properties/` — npy files for per-channel properties (`gain_to_uV`, `offset_to_uV`, `location`, `group`, `contact_vector`).
- `si_folder.json` — SpikeInterface folder metadata.

Loadable with `spikeinterface.full.load("…")`.

### 01 — Job dispatch (`obi-output/01_aind_ephys_dispatch/grid_scan/0/`)

- **`job_0.json`** — the dispatcher's serialised job recipe. Top-level keys: `session_name`, `recording_name`, `recording_dict` (a serialised SpikeInterface recording with paths relative to the capsule's `data/` so it absolute-resolves to the toy recording on disk), `skip_times`, `duration`, `input_folder`, `debug`, `multi_input`. Every downstream stage that needs the raw recording (02, 06, 08, 10, 11) re-loads it via `si.load(job["recording_dict"], base_folder=…)`.

### 02 — Preprocessing (`obi-output/02_aind_ephys_preprocessing/grid_scan/0/`)

For each recording (`<name> = block0_None_recording1`):

- **`preprocessed_<name>/`** — a SpikeInterface `BinaryFolderRecording` with the CMR-denoised, highpass-filtered, bad-channel-removed traces. `binary.json`, `traces_cached_seg0.raw`, `probe.json`, `provenance.json`, `properties/`, `si_folder.json` (same layout as 00 but with the preprocessing chain baked in).
- **`binary_<name>.json`** — a stand-alone "lazy" SpikeInterface JSON that reconstructs the same preprocessed recording (without copying samples) for downstream code that needs to chain its own steps.
- **`preprocessed_<name>.json`** — a "deep" SpikeInterface JSON describing the full preprocessing graph (load → filter → denoise → bad-channel removal). Used by visualization & QC capsules to reconstruct the lazy chain.
- **`preprocessedviz_<name>.json`** — pre-computed values the visualization capsule reuses for the drift map (peak detection / localization on the preprocessed recording).
- **`data_process_preprocessing_<name>.json`** — AIND-data-schema `DataProcess` provenance record (capsule version, parameters, runtime, software versions).

### 03 — Spike sorting / Kilosort4 (`obi-output/03_aind_ephys_spikesort_kilosort4/grid_scan/0/`)

- **`spikesorted_<name>/`** — a SpikeInterface `NumpyFolderSorting` produced by Kilosort4. Contains:
  - `spikes.npy` — structured array with `(sample_index, unit_index, segment_index)` per spike.
  - `numpysorting_info.json` — frame range + sampling frequency.
  - `properties/` — per-unit npy properties (`Amplitude`, `ContamPct`, `KSLabel` ('good'/'mua'), `original_cluster_id`, …).
  - `provenance.json`, `si_folder.json`, `spikeinterface_log.json` — reconstruction info + sorter runtime log.
- **`data_process_spikesorting_<name>.json`** — AIND DataProcess provenance.

Loadable with `si.load(spikesorted_…)` → `NumpyFolderSorting`.

### 04 — Postprocessing (`obi-output/04_aind_ephys_postprocessing/grid_scan/0/`)

- **`postprocessed_<name>.zarr/`** — a SpikeInterface `SortingAnalyzer` (zarr format) with the recording, sorting, and 13 computed extensions: `random_spikes`, `noise_levels`, `templates`, `waveforms`, `spike_amplitudes`, `template_similarity`, `correlograms`, `isi_histograms`, `unit_locations`, `spike_locations`, `template_metrics`, `principal_components`, `quality_metrics`. The `quality_metrics` extension contains a 26-column dataframe (firing_rate, presence_ratio, snr, isi_violations_ratio, amplitude_cutoff, drift_*, sliding_rp_violation, amplitude_cv_*, sync_spike_*, mahalanobis, …).
- **`data_process_postprocessing_<name>.json`** — AIND DataProcess provenance.

Loadable with `si.load_sorting_analyzer("postprocessed_….zarr")`.

### 05 — Curation (`obi-output/05_aind_ephys_curation/grid_scan/0/`)

- **`qc_<name>.npy`** — boolean numpy array, one entry per unit. `True` = unit passes the default QC pandas-query (`isi_violations_ratio < 0.5 and presence_ratio > 0.8 and amplitude_cutoff < 0.1`), `False` otherwise.
- **`unit_classifier_<name>.csv`** — per-unit `decoder_label` (`noise` / `sua` / `mua`) and `decoder_probability`, produced by chaining the HuggingFace `UnitRefine_noise_neural_classifier` and `UnitRefine_sua_mua_classifier` skops models.
- **`data_process_curation_<name>.json`** — AIND DataProcess provenance.

### 06 — Visualization (`obi-output/06_aind_ephys_visualization/grid_scan/0/`)

- **`visualization_<name>/`** — three matplotlib PNGs at 300 dpi:
  - `traces_full_seg0.png` — 2 × 0.5 s raw-trace snippets (full-band).
  - `traces_proc_seg0.png` — same time-windows on the preprocessed recording.
  - `drift_map.png` — drift map from spike-sorted detected peaks (peak detection threshold 5, localisation radius 100 µm).
- **`data_process_visualization_<name>.json`** — AIND DataProcess provenance.

(Without `KACHERY_API_KEY`, the figurl/sortingview uploads are skipped and the timeseries / sorting-summary URLs are empty.)

### 07 — Results collector (`obi-output/07_aind_ephys_results_collector/grid_scan/0/`)

A unified AIND-data-schema layout aggregating every previous stage:

- **`preprocessed/<name>.json`** — copy of `preprocessed_<name>.json` from 02.
- **`spikesorted/<name>/`** — copy of `spikesorted_<name>/` from 03.
- **`postprocessed/<name>.zarr/`** — copy of `postprocessed_<name>.zarr/` from 04 (with absolute paths re-mapped).
- **`curated/<name>/`** — sorting metadata associated to the curation outputs.
- **`visualization/<name>/`** — copy of the visualization figures from 06.
- **`processing.json`** — AIND-data-schema `Processing` document with one `data_processes` entry per stage (`Ephys preprocessing`, `Spike sorting`, `Ephys postprocessing`, `Ephys curation`, `Ephys visualization`) + a single `pipelines` entry called "AIND Ephys Pipeline".
- **`data_description.json`** — AIND-data-schema `DataDescription` (subject, modality, institution, creation_time, …).
- **`subject.json`** — synthesised subject record (the task creates a minimal `ecephys_<session>/subject.json` so the capsule's `assert len(ecephys_sessions) == 1` passes).
- **`visualization_output.json`** — top-level summary (kachery URLs etc., empty here).

### 08 — Processing QC (`obi-output/08_aind_ephys_processing_qc/grid_scan/0/`)

- **`quality_control_<name>.json`** — AIND-data-schema `QualityControl` document with 5 metrics:
  - Stage **Raw data**: `Raw data <name>` (links to `traces_raw.png`), `PSD <name>` (`psd.png`), `RMS <name>` (`rms.png`).
  - Stage **Processing**: `Unit Metrics Yield - <name>` (`unit_yield.png`), `Firing rate - <name>` (`firing_rate.png`).
- **`quality_control_<name>/`** — directory with the 5 PNGs referenced above.

### 09 — QC collector (`obi-output/09_aind_ephys_qc_collector/grid_scan/0/`)

- **`quality_control.json`** — single aggregated `QualityControl` document with all 5 metrics from 08, `default_grouping=['probe', 'stage']`, `allow_tag_failures=[]`. Each metric's `reference` was rewritten to point at the new flat figure tree.
- **`quality_control/<probe>/`** — flat figure tree (`<probe>` is the abbreviated probe name, here `block0_None`); contains the 5 PNGs from 08 deduplicated across recordings.

### 10 — ecephys NWB (`obi-output/10_aind_ecephys_nwb/grid_scan/0/`)

- **`<session>_<block>_<recording>.nwb`** (~76 MB) — pynwb HDF5 file:
  - `session_id`, `identifier`, `session_start_time` populated.
  - `devices`: 1 (`Probe`).
  - `electrode_groups`: 1 (`Probe`), 70 electrodes with `x/y/z`, `imp`, `location`, `filtering`, `group`.
  - `acquisition.ElectricalSeriesProbe`: shape `(300 000, 70)`, dtype int16, the raw float32 traces converted to int16 with a per-channel `gain_to_uV` / `offset_to_uV`.

### 11 — units NWB (`obi-output/11_aind_units_nwb/grid_scan/0/`)

- **`<session>_<block>_<recording>.nwb`** (~79 MB) — same NWB as 10 with a `units` table appended (one row per curated unit). Default columns: `spike_times`, `electrodes`, `waveform_mean`, `waveform_sd`. Plus all postprocessing + curation metrics surfaced as extra columns: `unit_name` (UUID), `ks_unit_id`, `device_name`, `shank`, `amplitude`, `depth`, `extremum_channel_index`, `estimated_x/y/z`, every quality metric (`firing_rate`, `presence_ratio`, `snr`, `isi_violations_ratio`, `amplitude_cutoff`, `silhouette`, `d_prime`, `mahalanobis`, …), every template metric (`peak_half_width`, `trough_half_width`, `peak_to_trough_duration`, `repolarization_slope`, `recovery_slope`, `velocity_above`, `velocity_below`, `spread`, …), and the curation outputs (`decoder_label`, `decoder_probability`, `default_qc`).

## In-place patches applied to upstream capsules

Several capsules were authored against an older spikeinterface (≤ 0.103) or older neuroconv. The OBI tasks patch the cloned `/tmp/aind-*/code/` files in place on first run so the capsules work against current `spikeinterface==0.104.x` and current `neuroconv`. The original GitHub repos are untouched.

| # | Capsule | Patches applied by the task | Why |
|---|---|---|---|
| 04 | aind-ephys-postprocessing | `qm_params=quality_metrics_params` → `metric_params=quality_metrics_params` in `code/run_capsule.py` | Newer spikeinterface renamed the kwarg of `SortingAnalyzer.compute("quality_metrics", …)`. |
| 04 | aind-ephys-postprocessing (config-side, applied via `params_dict()` rather than as a code patch) | `template_metrics.sparsity` is **not** emitted; `quality_metrics_names` swaps `l_ratio` / `isolation_distance` → `mahalanobis`; per-metric configs filtered to only the still-valid metric names. | Newer `ComputeTemplateMetrics` rejects `sparsity`; `l_ratio` / `isolation_distance` were merged into `mahalanobis`; deprecated `nn_isolation` / `nn_noise_overlap` blocks would fail validation. |
| 05 | aind-ephys-curation | `scikit-learn==1.5.2` pinned in the install cell. | The HuggingFace `SpikeInterface/UnitRefine_*` skops models were trained against sklearn 1.5; loading them under 1.8 fails with `'SimpleImputer' object has no attribute '_fill_dtype'`. |
| 08 | aind-ephys-processing-qc | In `code/qc_utils.py`: `spre.bandpass_filter(recording, freq_min=0.1, freq_max=freq_lfp)` → `…, ignore_low_freq_error=True)`. | Newer spikeinterface guards against sub-Hz bandpass cutoffs. |
| 08 | aind-ephys-processing-qc | In `code/qc_utils.py`: `template_metrics['half_width']` → `template_metrics['trough_half_width']`. | Newer spikeinterface renamed the column. |
| 10 | aind-ecephys-nwb | In `code/run_capsule.py`: `add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`. | Renamed in newer neuroconv. |
| 11 | aind-units-nwb | In `code/utils.py`: `add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`; `add_units_table_to_nwbfile` → `_add_units_table_to_nwbfile` (now private). Both rewrites are guarded so re-runs don't compound underscores. | Renamed / privatised in newer neuroconv. |

## Where `job_0.json` is used

`obi-output/01_aind_ephys_dispatch/grid_scan/0/job_0.json` is the dispatcher's serialised `recording_dict` — it encodes which raw data each downstream stage should load. Notebooks that consume it directly: **02** (preprocessing), **06** (visualization — for trace snippets), **07** (results-collector — copies it into the layout), **08** (processing-qc — for raw-data metrics), **10** (ecephys-nwb — for the raw `ElectricalSeries`), **11** (units-nwb — for waveforms / electrodes lookup). Notebooks that don't touch it: 00, 03 (uses notebook 02's preprocessed binary), 04 (uses preprocessed binary + sorting), 05 (uses postprocessed zarr only), 09 (operates on QC JSON files only).

## Output layout

```
obi-output/
├── 00_toy_example_recording/                                 # SpikeInterface BinaryFolderRecording
├── 01_aind_ephys_dispatch/grid_scan/0/                       # job_0.json
├── 02_aind_ephys_preprocessing/grid_scan/0/                  # preprocessed_<name>/, binary_<name>.json, …
├── 03_aind_ephys_spikesort_kilosort4/grid_scan/0/            # spikesorted_<name>/
├── 04_aind_ephys_postprocessing/grid_scan/0/                 # postprocessed_<name>.zarr (SortingAnalyzer)
├── 05_aind_ephys_curation/grid_scan/0/                       # qc_<name>.npy, unit_classifier_<name>.csv
├── 06_aind_ephys_visualization/grid_scan/0/                  # visualization_<name>/{drift_map,traces_*}.png
├── 07_aind_ephys_results_collector/grid_scan/0/              # AIND layout + processing.json + data_description.json
├── 08_aind_ephys_processing_qc/grid_scan/0/                  # quality_control_<name>.json + 5 PNGs
├── 09_aind_ephys_qc_collector/grid_scan/0/                   # aggregated quality_control.json + figure tree
├── 10_aind_ecephys_nwb/grid_scan/0/                          # <session>_<block>_<recording>.nwb (raw)
└── 11_aind_units_nwb/grid_scan/0/                            # same NWB + units table
```

## Notes on running locally

- All capsules are cloned to `/tmp/aind-*` on first run; subsequent runs reuse the clone (and its applied patches).
- KS4 runs on CPU here (no CUDA). For the toy data this takes ~10–15 s.
- The HuggingFace classifiers in 05 download a few MB on first run; subsequent runs are cached.
- No `KACHERY_API_KEY` is set, so 06 only writes local PNGs.
