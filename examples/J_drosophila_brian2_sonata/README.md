# 3D plot of neurons in the philshiu/Drosophila_brain_model

`plot_neuron_coordinates_3d.ipynb` plots the somata of every neuron in the
[philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model)
in 3D, coloured by FlyWire super-class.

## Why this notebook exists

The Drosophila_brain_model repo addresses neurons by their **FlyWire `root_id`**
but ships no spatial information — only `Completeness_783.csv` (the neuron list)
and `Connectivity_783.parquet` (the wiring). To plot the model in space we need
to fetch coordinates from FlyWire and join them on `root_id`.

## Data sources

| File | Source | Size | Provides |
|---|---|---|---|
| `Completeness_783.csv` | [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model/blob/main/Completeness_783.csv) | 3.3 MB | The 138 639 FlyWire `root_id`s that make up the model |
| `Supplemental_file1_neuron_annotations.tsv` | [flyconnectome/flywire_annotations](https://github.com/flyconnectome/flywire_annotations/blob/main/supplemental_files/Supplemental_file1_neuron_annotations.tsv) | 32.6 MB | Per-neuron annotations for FlyWire 783 — including `pos_x/y/z` and `soma_x/y/z` |

Both are downloaded once and cached under `~/.cache/flywire_783/`.

## What the notebook does

1. Downloads (with cache) the neuron list and the FlyWire 783 annotations.
2. Inner-joins them on `root_id`.
3. For each neuron picks `soma_x/y/z` if available, otherwise falls back to the
   anchor `pos_x/y/z`.
4. Converts FlyWire voxel space (4 × 4 × 40 nm) to micrometres.
5. Renders:
   - a 3D scatter of all 138 617 matched neurons coloured by `super_class`,
   - three 2D orthogonal projections (frontal / horizontal / sagittal),
   - an optional Plotly interactive view (skipped cleanly if Plotly is not
     installed).
6. Writes the joined coordinate table to
   `~/.cache/flywire_783/model_neuron_coordinates_783.csv`
   (138 617 rows: `root_id, x_um, y_um, z_um, super_class, side, top_nt`).

## Coordinate convention

The annotations TSV stores **voxel coordinates in 4 × 4 × 40 nm space**, the
native FlyWire/FAFB resolution. The notebook converts to micrometres:

```
x_um = pos_x * 4  / 1000
y_um = pos_y * 4  / 1000
z_um = pos_z * 40 / 1000
```

Two coordinate columns are available per neuron:

- `soma_x/y/z` — centre of the cell body, drawn from FlyWire's `nuclei_v1`
  table. Empty when no nucleus could be matched (see "Gaps" below).
- `pos_x/y/z` — an anchor coordinate, a representative point inside the
  segmentation. Always populated.

The notebook prefers `soma_*` and falls back to `pos_*` so every neuron gets
plotted.

The y-axis is inverted in all plots so the orientation matches the standard
FlyWire/FAFB convention (dorsal up).

## Coverage and gaps

Of the 138 639 model neurons:

- **138 617 (100.0 %)** match a row in the annotations TSV.
- **22 (0.02 %)** do not. Both files are pinned to FlyWire release 783, but the
  annotations file is regenerated periodically and a small number of segments
  get merged/split by proofreading touch-ups even within a release. Those 22
  `root_id`s in `Completeness_783.csv` were superseded by other IDs in the
  latest annotations dump. They could be recovered through the CAVE client
  (`chunkedgraph.get_latest_roots`) if needed.
- **118 078 (85.2 %)** of the matched neurons have a soma coordinate.
- **20 539 (14.8 %)** do not — the notebook falls back to `pos_x/y/z` for
  these.

The missing-soma cases are not data quality issues — they are an anatomical
limitation of the FAFB imaged volume. `nuclei_v1` only fires when the cell
body is inside FAFB:

| super_class | fraction with no soma | reason |
|---|---|---|
| `ascending` | 100 % (1 736) | somata in the ventral nerve cord, not in FAFB |
| `sensory_ascending` | 100 % (581) | somata in the VNC |
| `sensory` | 99.9 % (16 343) | somata in peripheral organs (ommatidia, antennae, bristles) |
| `optic` | 2.4 % (1 856) | mostly photoreceptor / lamina cells whose somata sit in the retina and were cropped at the volume boundary |
| `visual_projection`, `visual_centrifugal`, `central` | < 0.3 % | segmentation artefacts (soma unmerged or lost) |
| `descending`, `motor`, `endocrine` | 0 % | — |

For ascending and sensory neurons the `pos_*` anchor is the projection point
in the brain, **not** the cell body — worth keeping in mind when interpreting
those classes' positions.

## How to run

From the repo root, with the project venv:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute \
  examples/J_drosophila_brian2_sonata/plot_neuron_coordinates_3d.ipynb \
  --output plot_neuron_coordinates_3d.ipynb
```

Or open it in JupyterLab and run all cells. The first run takes ~30 s
(downloads ~36 MB); subsequent runs read from the cache.

Required packages: `pandas`, `numpy`, `matplotlib` (already in the project
venv). `plotly` is optional.

## Output

- Inline figures inside the notebook (3D scatter + 2D projections).
- `~/.cache/flywire_783/model_neuron_coordinates_783.csv` — the joined
  coordinate table, ready for downstream analysis.

## SONATA `node_sets.json`

Alongside the notebook is a [SONATA-format `node_sets.json`](node_sets.json)
that defines **127 named populations** of neurons in the model, ranging from
brain-wide groupings down to individual cell-type families. The sets are
attribute-based queries against the FlyWire annotation columns
(`flow`, `super_class`, `cell_class`, `cell_sub_class`, `cell_type`, `top_nt`,
`side`, `nerve`, `ito_lee_hemilineage`), so they apply to any SONATA nodes
file that exposes those columns as node attributes. Compound sets (lists of
references) are used for unions; `$regex` is used for cell-type-prefix
families (e.g. `^T4`, `^Mi[0-9]`).

The hierarchy follows Schlegel et al. 2024 ([Whole-brain annotation and
multi-connectome cell typing of Drosophila](https://www.nature.com/articles/s41586-024-07686-5)):
**flow → super_class → class → cell_type**. Region nomenclature follows the
standard Ito et al. 2014 insect-brain naming used throughout the FlyWire
papers (Dorkenwald et al. 2024, [Neuronal wiring diagram of an adult brain](https://www.nature.com/articles/s41586-024-07967-z);
Schlegel et al. 2024, ibid.).

### Set families

| Prefix | Granularity | Sets | Notes |
|---|---|---|---|
| (top-level) | model-wide | `All`, `Intrinsic`, `Afferent`, `Efferent` | by `flow` |
| `super_class__` | coarse | 10 sets — `optic`, `central`, `sensory`, `visual_projection`, `visual_centrifugal`, `ascending`, `sensory_ascending`, `descending`, `motor`, `endocrine` | Schlegel super-classes |
| (compound) | macro-region | `Optic_lobe`, `Central_brain`, `Sensory_periphery`, `Brain_outputs` | unions of super-classes |
| `side__` | hemisphere | `left`, `right`, `center` | |
| `nt__` | neurotransmitter | `acetylcholine`, `glutamate`, `gaba`, `dopamine`, `serotonin`, `octopamine` | from `top_nt` |
| `OL__` | optic lobe | 19 sets: 4 sub-regions (`lamina`, `medulla`, `lobula`, `lobula_plate`), photoreceptors (`R1-6`, `R7`, `R8`), lamina monopolars (`L1-5`), columnar families (`T4`, `T5`, `Mi`, `Tm`, `TmY`, `Dm`, `Pm`), output families (`LC`, `LPLC`, `LPC`, `LPi`, `LT`), `DRA` | sub-regions are unions over `cell_class` codes like `ME>LO`, `LA>ME` |
| `MB__` | mushroom body | 11 sets: `Kenyon_cells`, `KCab`, `KCab_p`, `KCgamma`, `KCapbp`, `MBON`, `MBIN`, `DAN`, `APL`, `DPM`, `MB__all` | the 5 principal MB classes from Schlegel 2024 |
| `AL__` | antennal lobe | `ALPN`, `ALLN`, `ALIN`, `ALON`, `mAL`, `multiglomerular_PNs`, `uniglomerular_PNs`, `AL__all` | olfactory pathway |
| `LH__` | lateral horn | `local_neurons`, `centrifugal_neurons`, `LH__all` | |
| `CX__` | central complex | 10 sets: `all_neurons`, `columnar`, `tangential`, `ring_neurons`, `EPG_compass`, `PEN`, `PEG`, `Delta7`, `ER_ring`, `FB_fan_shaped` | EB/FB/PB/NO components |
| `SENS__` | sensory modality | 8 modalities (`olfactory`, `mechanosensory`, `gustatory`, `visual`, `hygrosensory`, `thermosensory`, `ocellar`, JON `auditory`/`wind_gravity`), 3 bristle classes, 8 entry-nerve sets (`CV`, `AN`, `MxLbN`, `OCN`, `PhN`, `aPhN`, `NCC`, `ON`) | |
| `NE__` | neuroendocrine | `pars_intercerebralis`, `pars_lateralis`, `medial_NSC`, `lateral_NSC` | |
| `MOT__` | motor | `brain_motor`, `neck_motor`, `proboscis_motor`, `ingestion_motor` | |
| `DN__` | descending | `a`, `b`, `d`, `g`, `p`, `ge`, `pe` | DN soma-cluster suffixes (Namiki et al. 2018) |
| `CLOCK__` | circadian | `LNv`, `LNd`, `DN1p_clock`, `DN2_clock`, `DN3_clock`, `CLOCK__all` | NB: `DN1p`/`DN2`/`DN3` here are clock dorsal neurons, **not** descending neurons |
| `LIN__` | hemilineage | `MBp1`–`MBp4`, `LIN__MB_all` | mushroom-body primary lineages (Ito-Lee) |

All 127 sets were checked against the joined model+annotations table — every
set is non-empty.

### How to load with libsonata

```python
import libsonata
ns = libsonata.NodeSets.from_file(
    "examples/J_drosophila_brian2_sonata/node_sets.json"
)
ns.names              # list of all 127 set names
ns.materialize("OL__T4_neurons", nodes_population)   # returns a Selection
```

For downstream Brian2 / pandas use without libsonata, the same JSON can be
applied directly — the rules are simple column matches.

### References

- Dorkenwald et al. 2024. *Neuronal wiring diagram of an adult brain.*
  [Nature 634, 124–138](https://www.nature.com/articles/s41586-024-07967-z).
- Schlegel et al. 2024. *Whole-brain annotation and multi-connectome cell
  typing of Drosophila.*
  [Nature 634, 139–152](https://www.nature.com/articles/s41586-024-07686-5).
- Ito et al. 2014. *A systematic nomenclature for the insect brain.*
  Neuron 81, 755–765.
- Namiki et al. 2018. *The functional organization of descending sensory-motor
  pathways in Drosophila.* eLife 7:e34272.
