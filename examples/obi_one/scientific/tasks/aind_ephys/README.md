# AIND Ephys Pipeline Demo

End-to-end walk-through of the [AIND ephys pipeline](https://github.com/AllenNeuralDynamics/aind-ephys-pipeline) (job dispatch → preprocessing → spike sorting → postprocessing → curation → visualization → results collection → QC → NWB export) running locally on a small synthetic recording stored as NWB.

Each notebook builds an `AINDE…ScanConfig`, expands it via `GridScanGenerationTask`, and runs the corresponding `AINDE…Task` for each coordinate. Every stage's output lives under `obi-output/` (outside the repo). Every grid scan uses `coordinate_directory_option="ZERO_INDEX"` so coord 0 is always at `<output_root>/0/`.

The stages come in two kinds:

- **01–05 run in obi-one's own environment.** Their code is ported from the AIND repositories at the commits of pipeline release 1.5.0, with the defaults of its `default_params.json`, and calls spikeinterface 0.105 directly. They need obi-one's `spike-sorting` extra (`uv sync --extra spike-sorting`), and Kilosort4 also needs the `kilosort` extra. AIND-specific parts are left out: aind-data-schema metadata (each stage writes a plain `data_process_<stage>_<name>.json` instead), Code Ocean environment variables and the non-NWB input formats.
- **06–11 still wrap the upstream capsules.** Each task clones its capsule into `/tmp/`, runs `code/run_capsule.py` in an isolated virtual environment, and copies the results into `coordinate_output_root`. They are next to be ported: the capsules now read their parameters from `../params.json`, which these wrappers predate.

## Run order

Run the notebooks in numerical order (00 → 11). Each stage reads the previous stages' `obi-output/<NN>_…/grid_scan/0/` folders directly.

## Notebooks

| # | Notebook | What it does | Reads from | Writes to |
|---|---|---|---|---|
| 00 | `00_generate_toy_recording.ipynb` | Writes a 10 s, 32-channel, 10-unit ground-truth recording of one probe as NWB, with the probe geometry in the electrodes table, and saves the ground-truth sorting beside it. | — | `obi-output/00_toy_example_recording/toy_recording.nwb`, `ground_truth_sorting/` |
| 01 | `01_aind_ephys_dispatch.ipynb` | Port of [aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch) for NWB input: one job per ElectricalSeries in acquisition, split by segment and probe group. | `obi-output/00_toy_example_recording/` | `obi-output/01_aind_ephys_dispatch/grid_scan/0/job_0.json` |
| 02 | `02_aind_ephys_preprocessing.ipynb` | Port of [aind-ephys-preprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing) on a 9 s clip. It dispatches the NWB file itself, then applies highpass filter, bad-channel removal and common median reference, then motion estimation. | `obi-output/00_toy_example_recording/toy_recording.nwb` | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/job_<i>.json`, `preprocessed_<name>/`, `binary_<name>.json`, `motion_<name>/`, … |
| 03 | `03_aind_ephys_spikesorting.ipynb` | Port of the AIND sorter steps ([kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4), [spykingcircus2](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-spykingcircus2), [lupin](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-lupin)), with the sorter chosen by a block. Sorts notebook 02's output with Kilosort4 on CPU and scores it against the ground truth. | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/` | `obi-output/03_aind_ephys_spikesorting/grid_scan/0/spikesorted_<name>/` |
| 04 | `04_aind_ephys_postprocessing.ipynb` | Port of [aind-ephys-postprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing): duplicate removal, then a `SortingAnalyzer` with its extensions and quality metrics. | `obi-output/02_…/grid_scan/0/`, `obi-output/03_…/grid_scan/0/` | `obi-output/04_aind_ephys_postprocessing/grid_scan/0/postprocessed_<name>.zarr` |
| 05 | `05_aind_ephys_curation.ipynb` | Port of [aind-ephys-curation](https://github.com/AllenNeuralDynamics/aind-ephys-curation): default QC, UnitRefine and Bombcell labels, noise flagging and SLAy merge proposals. | `obi-output/04_aind_ephys_postprocessing/grid_scan/0/` | `obi-output/05_aind_ephys_curation/grid_scan/0/unit_labels_<name>.csv`, `unit_merges_<name>.json`, `curation_<name>.json` |
| 06 | `06_aind_ephys_visualization.ipynb` | Runs [aind-ephys-visualization](https://github.com/AllenNeuralDynamics/aind-ephys-visualization). Without a `KACHERY_API_KEY`, only emits local PNGs (drift map, raw + preprocessed traces). | `obi-output/01_…/grid_scan/0/`, `obi-output/02_…/grid_scan/0/`, `obi-output/04_…/grid_scan/0/`, `obi-output/05_…/grid_scan/0/` | `obi-output/06_aind_ephys_visualization/grid_scan/0/visualization_<name>/*.png` |
| 07 | `07_aind_ephys_results_collector.ipynb` | Runs [aind-ephys-results-collector](https://github.com/AllenNeuralDynamics/aind-ephys-results-collector). Aggregates the previous stages into `{preprocessed,spikesorted,postprocessed,curated,visualization}/` plus the AIND-data-schema `processing.json` / `data_description.json`. The task synthesises a minimal `ecephys_<session>/` folder so the capsule's `assert len(ecephys_sessions) == 1` passes. | `obi-output/01_…`, `obi-output/02_…`, `obi-output/03_…`, `obi-output/04_…`, `obi-output/05_…`, `obi-output/06_…` | `obi-output/07_aind_ephys_results_collector/grid_scan/0/{preprocessed,spikesorted,postprocessed,curated,visualization}/` + `processing.json` + `data_description.json` + `subject.json` |
| 08 | `08_aind_ephys_processing_qc.ipynb` | Runs [aind-ephys-processing-qc](https://github.com/AllenNeuralDynamics/aind-ephys-processing-qc) on the collected layout. | `obi-output/07_…/grid_scan/0/`, `obi-output/01_…/grid_scan/0/` | `obi-output/08_aind_ephys_processing_qc/grid_scan/0/quality_control_<name>.json` (5 metrics) + 5 PNGs |
| 09 | `09_aind_ephys_qc_collector.ipynb` | Runs [aind-ephys-qc-collector](https://github.com/AllenNeuralDynamics/aind-ephys-qc-collector). Aggregates per-recording QC into a single `quality_control.json` plus a flat `quality_control/<probe>/` figure tree. | `obi-output/08_…/grid_scan/0/` | `obi-output/09_aind_ephys_qc_collector/grid_scan/0/quality_control.json`, `quality_control/<probe>/*.png` |
| 10 | `10_aind_ecephys_nwb.ipynb` | Runs [aind-ecephys-nwb](https://github.com/AllenNeuralDynamics/aind-ecephys-nwb). Writes one HDF5 NWB per (block, recording) with the raw `ElectricalSeries`. Flags: `--write-raw --skip-lfp`. | `obi-output/01_…/grid_scan/0/` | `obi-output/10_aind_ecephys_nwb/grid_scan/0/<session>_<block>_<recording>.nwb` (~76 MB) |
| 11 | `11_aind_units_nwb.ipynb` | Runs [aind-units-nwb](https://github.com/AllenNeuralDynamics/aind-units-nwb). Appends the curated sorting + waveforms to the base NWB. | `obi-output/10_…/grid_scan/0/`, `obi-output/07_…/grid_scan/0/{postprocessed,curated,spikesorted}/`, `obi-output/01_…/grid_scan/0/` | `obi-output/11_aind_units_nwb/grid_scan/0/<session>_<block>_<recording>.nwb` (~79 MB, with `units` table) |

## What each output actually contains

The OBI framework always writes two metadata files alongside a stage's own output:

- **`obi_one_scan.json`** at `<output_root>/` — the serialised `ScanConfig` (every parameter the user set).
- **`obi_one_coordinate.json`** at `<output_root>/<idx>/` — the serialised `SingleConfig` for that one coordinate (concrete values for sweep dims).

A recording a stage skips (too short, too many bad channels, failed sorting) gets its output folder with only an `error.txt` inside, and later stages skip it too. Each ported stage also writes `data_process_<stage>_<name>.json`: the parameters it used, its outputs (such as channel labels or unit counts) and notes.

### 00 — Toy recording (`obi-output/00_toy_example_recording/`)

- **`toy_recording.nwb`** — one raw `ElectricalSeries` in acquisition, with one `Device` and `ElectrodeGroup` (`ToyProbe`) and the contact positions as `rel_x`/`rel_y` in the electrodes table.
- **`ground_truth_sorting/`** — the spikes the recording was generated from, as a SpikeInterface `NumpyFolderSorting`.

### 01 — Job dispatch (`obi-output/01_aind_ephys_dispatch/grid_scan/0/`)

Standalone, for inspecting the jobs. Preprocessing makes the same jobs itself, so notebook 02 doesn't need this one.

- **`job_0.json`** — top-level keys `session_name`, `recording_name`, `recording_dict` (the recording serialised relative to `input_folder`), `input_folder` (the NWB file's folder), `skip_times`, `duration` and `debug`. The recording's probe carries the NWB device's name and description.

### 02 — Preprocessing (`obi-output/02_aind_ephys_preprocessing/grid_scan/0/`)

For each recording (`<name> = block0_acquisition-ElectricalSeriesRaw_recording1`):

- **`job_<i>.json`** — the dispatched jobs, as notebook 01 writes them. Stages 06–11 can take this folder as their `dispatch_output_path`.
- **`preprocessed_<name>/`** — the preprocessed traces, as a SpikeInterface `BinaryFolderRecording`.
- **`binary_<name>.json`** — reloads that binary folder (paths relative to this folder); what the later stages read.
- **`preprocessed_<name>.json`** — the lazy preprocessing chain over the raw NWB recording (absolute paths).
- **`motion_<name>/`** — the motion estimate, loadable with `spikeinterface.preprocessing.load_motion_info`, and **`motioncorrected_<name>.json`** when motion is applied.

### 03 — Spike sorting (`obi-output/03_aind_ephys_spikesorting/grid_scan/0/`)

- **`spikesorted_<name>/`** — the sorting as a SpikeInterface `NumpyFolderSorting`, without empty units or spikes beyond the recording, plus the sorter's `spikeinterface_log.json`.
- **`spikesortedmotion_<name>/`** — Kilosort4's own motion estimate, when it corrected drift (probes with at least `min_drift_channels` channels).

### 04 — Postprocessing (`obi-output/04_aind_ephys_postprocessing/grid_scan/0/`)

- **`postprocessed_<name>.zarr/`** — a SpikeInterface `SortingAnalyzer` with `random_spikes`, `noise_levels`, `waveforms`, `templates`, `spike_amplitudes`, `template_similarity`, `correlograms`, `isi_histograms`, `unit_locations`, `spike_locations`, `template_metrics`, `principal_components`, `amplitude_scalings`, `valid_unit_periods` and `quality_metrics`.
- Load it with `obi_one.scientific.tasks.aind_ephys.utils.load_analyzer`, which skips `principal_components`: its fitted PCA models are pickled, and numcodecs refuses to decode pickles since 0.15.2.

### 05 — Curation (`obi-output/05_aind_ephys_curation/grid_scan/0/`)

- **`unit_labels_<name>.csv`** — one row per unit (`unit_id`) with `default_qc` (pass/fail of the QC thresholds), `unitrefine_label` and `unitrefine_probability` (noise/sua/mua) and `bombcell_label` (good/mua/noise/non_soma).
- **`unit_merges_<name>.json`** — the groups of neural units SLAy proposes to merge.
- **`curation_<name>.json`** — the noise units and proposed merges as a spikeinterface `Curation` (format 2), which `spikeinterface.curation.apply_curation` applies.

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

The capsule-based stages (06–11) patch the cloned `/tmp/aind-*/code/` files in place on first run so the capsules work against current `spikeinterface` and `neuroconv`. The original GitHub repos are untouched.

| # | Capsule | Patches applied by the task | Why |
|---|---|---|---|
| 08 | aind-ephys-processing-qc | In `code/qc_utils.py`: `spre.bandpass_filter(recording, freq_min=0.1, freq_max=freq_lfp)` → `…, ignore_low_freq_error=True)`. | Newer spikeinterface guards against sub-Hz bandpass cutoffs. |
| 08 | aind-ephys-processing-qc | In `code/qc_utils.py`: `template_metrics['half_width']` → `template_metrics['trough_half_width']`. | Newer spikeinterface renamed the column. |
| 10 | aind-ecephys-nwb | In `code/run_capsule.py`: `add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`. | Renamed in newer neuroconv. |
| 11 | aind-units-nwb | In `code/utils.py`: `add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`; `add_units_table_to_nwbfile` → `_add_units_table_to_nwbfile` (now private). Both rewrites are guarded so re-runs don't compound underscores. | Renamed / privatised in newer neuroconv. |

## Output layout

```
obi-output/
├── 00_toy_example_recording/                                 # toy_recording.nwb + ground_truth_sorting/
├── 01_aind_ephys_dispatch/grid_scan/0/                       # job_0.json
├── 02_aind_ephys_preprocessing/grid_scan/0/                  # preprocessed_<name>/, binary_<name>.json, motion_<name>/, …
├── 03_aind_ephys_spikesorting/grid_scan/0/                   # spikesorted_<name>/
├── 04_aind_ephys_postprocessing/grid_scan/0/                 # postprocessed_<name>.zarr (SortingAnalyzer)
├── 05_aind_ephys_curation/grid_scan/0/                       # unit_labels_<name>.csv, unit_merges_<name>.json, curation_<name>.json
├── 06_aind_ephys_visualization/grid_scan/0/                  # visualization_<name>/{drift_map,traces_*}.png
├── 07_aind_ephys_results_collector/grid_scan/0/              # AIND layout + processing.json + data_description.json
├── 08_aind_ephys_processing_qc/grid_scan/0/                  # quality_control_<name>.json + 5 PNGs
├── 09_aind_ephys_qc_collector/grid_scan/0/                   # aggregated quality_control.json + figure tree
├── 10_aind_ecephys_nwb/grid_scan/0/                          # <session>_<block>_<recording>.nwb (raw)
└── 11_aind_units_nwb/grid_scan/0/                            # same NWB + units table
```

## Notes on running locally

- Kilosort4 runs on CPU here (no CUDA); on the toy data it takes about 10 s. SpykingCircus2 and Lupin need no extra install.
- UnitRefine downloads its classifiers from Hugging Face on first run. They were trained with scikit-learn 1.4, so loading them under obi-one's newer scikit-learn prints `InconsistentVersionWarning`; they still predict. Set both classifiers to `None` in the `UnitRefine` block to skip it.
- On the 9 s toy recording the default QC fails every unit, because its presence-ratio and amplitude-cutoff thresholds assume long recordings.
- Capsules of the stages 06–11 are cloned to `/tmp/aind-*` on first run; subsequent runs reuse the clone (and its applied patches).
