# AIND Ephys Pipeline Demo

End-to-end walk-through of the [AIND ephys pipeline](https://github.com/AllenNeuralDynamics/aind-ephys-pipeline) (job dispatch → preprocessing → spike sorting) running locally on a small synthetic recording stored as NWB.

Each notebook builds an `AINDE…ScanConfig`, expands it via `GridScanGenerationTask`, and runs the corresponding `AINDE…Task` for each coordinate. Every stage's output lives under `obi-output/` (outside the repo). Every grid scan uses `coordinate_directory_option="ZERO_INDEX"` so coord 0 is always at `<output_root>/0/`.

The stages run in obi-one's own environment. Their code is ported from the AIND repositories at the commits of pipeline release 1.5.0, with the defaults of its `default_params.json`, and calls spikeinterface 0.105 directly. They need obi-one's `spike-sorting` extra (`uv sync --extra spike-sorting`), and Kilosort4 also needs the `kilosort` extra. AIND-specific parts are left out: aind-data-schema metadata (each stage writes a plain `data_process_<stage>_<name>.json` instead), Code Ocean environment variables and the non-NWB input formats.

## Run order

Run the notebooks in numerical order (00 → 03). Each stage reads the previous stages' `obi-output/<NN>_…/grid_scan/0/` folders directly.

## Notebooks

| # | Notebook | What it does | Reads from | Writes to |
|---|---|---|---|---|
| 00 | `00_generate_toy_recording.ipynb` | Writes a 10 s, 32-channel, 10-unit ground-truth recording of one probe as NWB, with the probe geometry in the electrodes table, and saves the ground-truth sorting beside it. | — | `obi-output/00_toy_example_recording/toy_recording.nwb`, `ground_truth_sorting/` |
| 01 | `01_aind_ephys_dispatch.ipynb` | Port of [aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch) for NWB input: one job per ElectricalSeries in acquisition, split by segment and probe group. | `obi-output/00_toy_example_recording/` | `obi-output/01_aind_ephys_dispatch/grid_scan/0/job_0.json` |
| 02 | `02_aind_ephys_preprocessing.ipynb` | Port of [aind-ephys-preprocessing](https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing) on a 9 s clip. It dispatches the NWB file itself, then applies highpass filter, bad-channel removal and common median reference, then motion estimation. | `obi-output/00_toy_example_recording/toy_recording.nwb` | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/job_<i>.json`, `preprocessed_<name>/`, `binary_<name>.json`, `motion_<name>/`, … |
| 03 | `03_aind_ephys_spikesorting.ipynb` | Port of the AIND sorter steps ([kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4), [spykingcircus2](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-spykingcircus2), [lupin](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-lupin)), one task per sorter with its parameters spread across blocks. Sorts notebook 02's output with Kilosort4 on CPU and scores it against the ground truth. | `obi-output/02_aind_ephys_preprocessing/grid_scan/0/` | `obi-output/03_aind_ephys_spikesorting/grid_scan/0/spikesorted_<name>/` |

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

## Output layout

```
obi-output/
├── 00_toy_example_recording/                                 # toy_recording.nwb + ground_truth_sorting/
├── 01_aind_ephys_dispatch/grid_scan/0/                       # job_0.json
├── 02_aind_ephys_preprocessing/grid_scan/0/                  # preprocessed_<name>/, binary_<name>.json, motion_<name>/, …
└── 03_aind_ephys_spikesorting/grid_scan/0/                   # spikesorted_<name>/
```

## Notes on running locally

- Kilosort4 runs on CPU here (no CUDA); on the toy data it takes about 10 s. SpykingCircus2 and Lupin need no extra install.
