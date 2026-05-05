# L_emodel_optimization — BluePyEModel L5PC Pipeline Demo

End-to-end walk-through of the four stages of the
[BluePyEModel L5PC example](https://github.com/openbraininstitute/BluePyEModel/blob/main/examples/L5PC/README.rst)
running locally on the SSCx C060109A1-SR-C1 dataset:

1. **eFeature extraction** — extract experimental e-features from raw IBW traces.
2. **Optimisation** — fit the L5PC model parameters with SO-CMA (single-objective CMA-ES).
3. **Analysis & validation** — `store_optimisation_results`, `validation`, `plot`.
4. **Export** — emit HOC and SONATA representations of the optimised model.

Each notebook builds the corresponding `obi.EModel…ScanConfig`, expands it via
`GridScanGenerationTask`, and runs the matching `EModel…Task` for every
coordinate. The task copies (or seeds, for stages 02-04) a self-contained
BluePyEModel working directory into the single config's `coordinate_output_root`
and `chdir`s into it before invoking the BluePyEModel API. Every stage's output
lives under `obi-output/` (outside the repo). With `coordinate_directory_option="ZERO_INDEX"`
coord 0 is always at `<output_root>/0/`; sweep dimensions add `1/`, `2/`, … alongside it.

## Prerequisites

- `bluepyemodel[nexus]` installed in the active venv (the setup notebook installs it via `uv pip`).
  The `[nexus]` extra is required because BluePyEModel's top-level import chain
  unconditionally imports `entity_management` / `nexusforge` / `pyJWT`, even when
  only the local access point is used.
- **NEURON 8.2.x**, not 9.x. The L5PC mechanism set ships with `StochKv2.mod` and
  `StochKv3.mod` which fail to compile under NEURON 9 (`nrn_random_pick(Rand*)`
  vs. `void*`). The setup notebook pins `neuron<9` to avoid the issue.
- `nrnivmodl` available — NEURON's mod-file compiler. The tasks resolve it via
  `shutil.which` first, then fall back to `<sys.prefix>/bin/nrnivmodl`, so the
  pip-installed NEURON in the venv works even if you haven't activated it.
- An internet connection for the first run of `00_setup_download_l5pc_data.ipynb`.

## Run order

| # | Notebook | What it does | Reads from | Writes to |
|---|---|---|---|---|
| 00 | [`00_setup_download_l5pc_data.ipynb`](00_setup_download_l5pc_data.ipynb) | Installs `bluepyemodel`; fetches the L5PC ephys data, recipe, params, morphology, and mod files. *No task — pure data setup.* | — | `obi-output/L_emodel_optimization_inputs/` |
| 01 | [`01_efeature_extraction.ipynb`](01_efeature_extraction.ipynb) | Materialises a BluePyEModel working directory, runs `configure_targets()` + `pipeline.extract_efeatures()`. | `obi-output/L_emodel_optimization_inputs/` | `obi-output/01_efeature_extraction/grid_scan/0/` |
| 02 | [`02_emodel_optimization.ipynb`](02_emodel_optimization.ipynb) | Seeds the working dir from stage 01, runs `pipeline.optimise(seed=...)` with `optimiser='SO-CMA'`, `max_ngen=2`, `offspring_size=4`. | `obi-output/01_efeature_extraction/grid_scan/0/` | `obi-output/02_emodel_optimization/grid_scan/0/` |
| 03 | [`03_analysis_and_validation.ipynb`](03_analysis_and_validation.ipynb) | Seeds from stage 02, runs `store_optimisation_results` → `validation` → `plot`. | `obi-output/02_emodel_optimization/grid_scan/0/` | `obi-output/03_analysis_and_validation/grid_scan/0/` |
| 04 | [`04_export_final_model.ipynb`](04_export_final_model.ipynb) | Seeds from stage 03, runs `export_emodels_hoc` and `export_emodels_sonata`. | `obi-output/03_analysis_and_validation/grid_scan/0/` | `obi-output/04_export_final_model/grid_scan/0/` |

## Output layout

```
obi-output/
├── L_emodel_optimization_inputs/                  # downloaded by the setup notebook
│   ├── ephys_data/C060109A1-SR-C1/                # *.ibw raw traces
│   ├── morphologies/C060114A5.asc
│   ├── mechanisms/*.mod
│   └── config/{params/pyr.json, recipes.json}
├── 01_efeature_extraction/grid_scan/0/            # working dir + features/L5PC.json + figures/
├── 02_emodel_optimization/grid_scan/0/            # working dir + checkpoints/ + run/
├── 03_analysis_and_validation/grid_scan/0/        # working dir + final.json + figures/
└── 04_export_final_model/grid_scan/0/             # working dir + export_emodels_hoc/ + export_emodels_sonata/
```

The OBI framework also writes `obi_one_scan.json` (the serialised `ScanConfig`)
and `obi_one_coordinate.json` (the serialised `SingleConfig` for that coord)
alongside whatever BluePyEModel produces.

## Tuning the demo

Stage 02 ships with **very small** generation/offspring counts so the demo runs
in minutes rather than hours. For production runs increase `max_ngen` to ~100
and `offspring_size` to ~20 (matching the L5PC example's recipe), and consider
sweeping `seed` to fit several models in parallel:

```python
optimization_settings=OptimizationSettings(
    optimiser="SO-CMA",
    max_ngen=100,
    offspring_size=20,        # via OptimizationParams
    seed=[1, 2, 3, 4, 5],     # five sweep coordinates
)
```

Setting any block field to a list turns it into a sweep dimension. Use tuples
when you want a stable list-valued parameter (e.g. `validation_protocols`).

## Other optimisers

`OptimizationSettings.optimiser` accepts `"SO-CMA"` (single-objective CMA-ES;
default in this demo), `"MO-CMA"` (multi-objective CMA-ES; the L5PC recipe
default), or `"IBEA"`. These are the three values
`bluepyemodel.optimisation.optimisation.setup_optimiser` knows how to dispatch.
The wrapping task writes the chosen value verbatim into the recipe's
`pipeline_settings`.
