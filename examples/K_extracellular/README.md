# K_extracellular — AIND Ephys Pipeline Demo

End-to-end walk-through of the [AIND ephys pipeline](https://github.com/AllenNeuralDynamics) (job dispatch → preprocessing → spike sorting → postprocessing → curation → visualization → results collection → QC → NWB export) running locally against a tiny synthetic SpikeInterface recording.

Each notebook clones the corresponding capsule from GitHub into `/tmp`, seeds its `data/` folder from the previous stages' outputs, runs the capsule's `run_capsule.py`, and copies the results into `output/<NN>_<name>/` next to the notebook. The whole `output/` tree is git-ignored.

## Run order

Run the notebooks in numerical order (00 → 11). Each stage depends on the on-disk outputs of the previous stages, all under `output/`.

## Notebooks

| # | Notebook | What it does | Reads from | Writes to | Needs `job_0.json`? |
|---|---|---|---|---|---|
| 00 | `00_generate_toy_recording.ipynb` | Installs `spikeinterface` and generates a 10 s, 70-channel, 10-unit ground-truth `BinaryFolderRecording` (`num_channels=70`). | — | `output/00_toy_example_recording/` | No |
| 01 | `01_aind_ephys_dispatch.ipynb` | Runs [aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch). Builds an `obi.AINDEPhysDispatchScanConfig` + `GridScanGenerationTask` to expand a parameter sweep, then invokes the dispatch CLI with `--input spikeinterface --spikeinterface-info '{...}'` against the toy recording. | `output/00_toy_example_recording/` | `output/01_dispatch_results/job_0.json` (**produces** it) | **Produces** |
| 02 | `02_aind_ephys_preprocessing.ipynb` | Runs [aind-ephys-preprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing) on a 1-second clip (`--t-stop 1`). Custom `params_toy.json` lowers `min_preprocessing_duration` and disables motion correction. | `output/01_dispatch_results/job_0.json` | `output/02_preprocessing_results/preprocessed_<name>/`, `binary_<name>.json`, `preprocessedviz_<name>.json`, `data_process_*.json` | **Yes** |
| 03 | `03_aind_ephys_spikesort_kilosort4.ipynb` | Re-runs preprocessing at 8 s (KS4 needs > 1 s for whitening), then runs [aind-ephys-spikesort-kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4). Custom `params_toy.json` disables drift correction and pins `torch_device: cpu`. | `output/01_dispatch_results/job_0.json` (used by re-run preprocessing) | `output/03_spikesort_results/spikesorted_<name>/` (~14 KS4 units) | **Yes** (for the inner preprocessing re-run) |
| 04 | `04_aind_ephys_postprocessing.ipynb` | Runs [aind-ephys-postprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing). Patches the capsule's params for spikeinterface API drift (`qm_params` → `metric_params`, `template_metrics.sparsity` removed, `l_ratio` / `isolation_distance` → `mahalanobis`). | preprocessing capsule's `results/`, `output/03_spikesort_results/` | `output/04_postprocessing_results/postprocessed_<name>.zarr` (`SortingAnalyzer` with quality + template metrics for 10 deduplicated units) | No |
| 05 | `05_aind_ephys_curation.ipynb` | Runs [aind-ephys-curation](https://github.com/AllenNeuralDynamics/aind-ephys-curation). Applies the default QC query and the HuggingFace `SpikeInterface/UnitRefine_*` noise-neural & SUA/MUA classifiers. Pins `scikit-learn==1.5.2` (skops models were trained against 1.5). | `output/04_postprocessing_results/postprocessed_<name>.zarr` | `output/05_curation_results/qc_<name>.npy`, `unit_classifier_<name>.csv` | No |
| 06 | `06_aind_ephys_visualization.ipynb` | Runs [aind-ephys-visualization](https://github.com/AllenNeuralDynamics/aind-ephys-visualization). Without a `KACHERY_API_KEY`, only emits local PNGs (drift map, raw + preprocessed traces). | `output/01_dispatch_results/`, preprocessing capsule's `results/`, `output/04_postprocessing_results/`, `output/05_curation_results/` | `output/06_visualization_results/visualization_<name>/*.png` | **Yes** |
| 07 | `07_aind_ephys_results_collector.ipynb` | Runs [aind-ephys-results-collector](https://github.com/AllenNeuralDynamics/aind-ephys-results-collector). Aggregates everything into `{preprocessed,spikesorted,postprocessed,curated,visualization}/...` plus generates the AIND-data-schema `processing.json` and `data_description.json`. Synthesises a minimal `ecephys_toy/` session folder so the capsule's `assert len(ecephys_sessions) == 1` passes. | preprocessing capsule's `results/`, `output/03_spikesort_results/`, `output/04_postprocessing_results/`, `output/05_curation_results/`, `output/06_visualization_results/`, `output/01_dispatch_results/` | `output/07_collected_results/{preprocessed,spikesorted,postprocessed,curated,visualization}/`, `processing.json`, `data_description.json` | **Yes** |
| 08 | `08_aind_ephys_processing_qc.ipynb` | Runs [aind-ephys-processing-qc](https://github.com/AllenNeuralDynamics/aind-ephys-processing-qc) on the collected layout. Patches `qc_utils.py` for spikeinterface API drift (`bandpass_filter` `ignore_low_freq_error`, `template_metrics['half_width']` → `'trough_half_width'`). | `output/07_collected_results/`, `output/01_dispatch_results/job_0.json` | `output/08_qc_results/quality_control_<name>.json` (5 metrics: Raw data {traces, PSD, RMS}, Processing {Unit yield, Firing rate}) + 5 PNGs | **Yes** |
| 09 | `09_aind_ephys_qc_collector.ipynb` | Runs [aind-ephys-qc-collector](https://github.com/AllenNeuralDynamics/aind-ephys-qc-collector). Aggregates per-recording `quality_control_*.json` into a single `quality_control.json` with `default_grouping=['probe', 'stage']` and a flat `quality_control/<probe>/` figure tree. | `output/08_qc_results/` | `output/09_qc_collected_results/quality_control.json`, `quality_control/<probe>/*.png` | No |
| 10 | `10_aind_ecephys_nwb.ipynb` | Runs [aind-ecephys-nwb](https://github.com/AllenNeuralDynamics/aind-ecephys-nwb). Patches a neuroconv API rename (`add_electrodes_info_to_nwbfile` → `add_electrodes_to_nwbfile`) and writes one HDF5 NWB per (block, recording) with the raw `ElectricalSeries`. | `output/01_dispatch_results/job_0.json` | `output/10_nwb_results/<session>_block0_recording1.nwb` (~76 MB) | **Yes** |
| 11 | `11_aind_units_nwb.ipynb` | Runs [aind-units-nwb](https://github.com/AllenNeuralDynamics/aind-units-nwb) to append the curated sorting to the base NWB. Patches two more neuroconv API renames. The resulting `units` table has UUIDs, KS unit ids, amplitude, depth, every quality + template metric, and the curation `decoder_label` / `default_qc`. | `output/10_nwb_results/`, `output/07_collected_results/{postprocessed,curated,spikesorted}/`, `output/01_dispatch_results/job_0.json` | `output/11_units_nwb_results/<session>_block0_recording1.nwb` (~78 MB) with `units` table | **Yes** |

## Where `job_0.json` is used

`output/01_dispatch_results/job_0.json` is the dispatcher's serialised `recording_dict` — a SpikeInterface JSON pointing at the toy recording with paths relative to `data/`. It encodes which raw data each downstream stage should load.

Notebooks that copy / require it directly:

- **02** — preprocessing seeds it into the capsule's `data/`.
- **03** — re-running preprocessing inside this notebook reuses the same `job_0.json` already in the preprocessing capsule's `data/`.
- **06** — visualization needs it to load the raw recording for trace snippets.
- **07** — results-collector copies it into the aggregated layout.
- **08** — processing-qc loads the raw recording from it for raw-data metrics.
- **10** — `aind-ecephys-nwb` reads `recording_dict` to write the raw `ElectricalSeries`.
- **11** — `aind-units-nwb` reads `recording_dict` to look up the recording when writing waveforms / electrodes.

Notebooks that don't touch `job_0.json` directly: 00, 04 (postprocessing — uses preprocessed binary), 05 (curation — uses postprocessed zarr), 09 (qc-collector — operates on QC JSON files only).

## Output layout

Everything each stage produces lives under `output/` (git-ignored):

```
output/
├── 00_toy_example_recording/
├── 01_dispatch_results/
├── 02_preprocessing_results/
├── 03_spikesort_results/
├── 04_postprocessing_results/
├── 05_curation_results/
├── 06_visualization_results/
├── 07_collected_results/
├── 08_qc_results/
├── 09_qc_collected_results/
├── 10_nwb_results/
└── 11_units_nwb_results/
```

| Folder | Produced by |
|---|---|
| `output/00_toy_example_recording/` | 00 |
| `output/01_dispatch_results/` | 01 |
| `output/02_preprocessing_results/` | 02 |
| `output/03_spikesort_results/` | 03 |
| `output/04_postprocessing_results/` | 04 |
| `output/05_curation_results/` | 05 |
| `output/06_visualization_results/` | 06 |
| `output/07_collected_results/` | 07 |
| `output/08_qc_results/` | 08 |
| `output/09_qc_collected_results/` | 09 |
| `output/10_nwb_results/` | 10 |
| `output/11_units_nwb_results/` | 11 |

## Notes on running locally

- All capsules are cloned to `/tmp/aind-*` on first run; subsequent runs reuse the clone.
- Several notebooks patch upstream capsule code or params for spikeinterface / neuroconv API drift — the patches are applied in-place to the cloned `/tmp` copy, so the upstream repos remain untouched.
- KS4 runs on CPU here (no CUDA). For the toy data this takes ~10 s.
- The HuggingFace classifiers in 05 download a few MB on first run; subsequent runs are cached.
- No `KACHERY_API_KEY` is set, so 06 only writes local PNGs.
