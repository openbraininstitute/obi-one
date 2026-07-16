# L_emodel_optimization — BluePyEModel L5PC Pipeline Demo

End-to-end walk-through of the three stages of the
[BluePyEModel L5PC example](https://github.com/openbraininstitute/BluePyEModel/blob/main/examples/L5PC/README.rst)
running on the SSCx C060109A1-SR-C1 dataset via entitycore staging:

1. **eFeature extraction** — download `ElectricalCellRecording` NWB assets from
   entitycore and extract experimental e-features via BluePyEModel's
   `extract_save_features_protocols`.
2. **Optimisation** — fit the L5PC model parameters with SO-CMA (single-objective
   CMA-ES). Downloads the extraction `TaskResult` assets, stages `CellMorphology`
   and `IonChannelModel` entities, builds params dynamically, and runs
   `pipeline.optimise(seed=...)` followed by analysis and draft emodel export.
3. **Export and validation** — download the optimisation `TaskResult` assets, run
   `store_optimisation_results` → `validation` → `plot`, then export validated
   models to HOC and SONATA. Updates the draft `MEModel` with calibration results.

Each notebook builds the corresponding `obi.EModel…ScanConfig`, expands it via
`GridScanGenerationTask`, and runs the matching `EModel…Task` for every
coordinate. The task seeds a self-contained BluePyEModel working directory into
the single config's `coordinate_output_root` and `chdir`s into it before invoking
the BluePyEModel API. Every stage's output lives under `obi-output/` (outside the
repo). With `coordinate_directory_option="ZERO_INDEX"` coord 0 is always at
`<output_root>/0/`; sweep dimensions add `1/`, `2/`, … alongside it.

All stages use **entity-based inputs** — `TaskResult`, `CellMorphology`,
`IonChannelModel`, and `MEModel` entities are fetched from entitycore staging
via `db_client`. Replace the placeholder entity IDs in each notebook with real
IDs from your staging project before running.

## Prerequisites

- `bluepyemodel` installed in the active venv.
- **NEURON 8.2.x**, not 9.x. The L5PC mechanism set ships with `StochKv2.mod` and
  `StochKv3.mod` which fail to compile under NEURON 9 (`nrn_random_pick(Rand*)`
  vs. `void*`).
- `nrnivmodl` available — NEURON's mod-file compiler. The tasks resolve it via
  `shutil.which` first, then fall back to `<sys.prefix>/bin/nrnivmodl`, so the
  pip-installed NEURON in the venv works even if you haven't activated it.
- Access to entitycore staging (the notebooks use `obi_auth.get_token(environment="staging")`
  which opens a browser tab for authentication).
- Real entity IDs in your staging project for `ElectricalCellRecording`,
  `CellMorphology`, `IonChannelModel`, `TaskResult`, and `MEModel` entities.

## Run order

| # | Notebook | What it does | Reads from | Writes to |
|---|---|---|---|---|
| 01 | [`01_efeature_extraction.ipynb`](01_efeature_extraction.ipynb) | Downloads `ElectricalCellRecording` NWB assets from entitycore, extracts e-features via BluePyEModel; writes `extracted_features.json` and a minimal `recipes.json`. Registers a `TaskResult` entity. | entitycore staging (`ElectricalCellRecording` entities) | `obi-output/01_efeature_extraction/grid_scan/0/` |
| 02 | [`02_emodel_optimization.ipynb`](02_emodel_optimization.ipynb) | Downloads extraction `TaskResult` assets, stages `CellMorphology` + `IonChannelModel` entities, builds params dynamically, runs `pipeline.optimise(seed=...)` with `optimiser='SO-CMA'`, `max_ngen=2`, `offspring_size=4`. Registers a `TaskResult` + draft `MEModel` entity. | entitycore staging (extraction `TaskResult`, `CellMorphology`, `IonChannelModel` entities) | `obi-output/02_emodel_optimization/grid_scan/0/` |
| 03 | [`03_export_and_validation.ipynb`](03_export_and_validation.ipynb) | Downloads optimisation `TaskResult` assets, runs `store_optimisation_results` → `validation` → `plot`, then `export_emodels_hoc` and `export_emodels_sonata`. Updates `MEModel` with calibration results. | entitycore staging (optimisation `TaskResult`, draft `MEModel` entities) | `obi-output/03_export_and_validation/grid_scan/0/` |

## Output layout

```
obi-output/
├── 01_efeature_extraction/grid_scan/0/            # ephys_data/ + extraction/ + extracted_features.json + config/recipes.json
├── 02_emodel_optimization/grid_scan/0/            # working dir + checkpoints/ + run/ + figures/
└── 03_export_and_validation/grid_scan/0/          # working dir + final.json + figures/ + export_emodels_hoc/ + export_emodels_sonata/
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
