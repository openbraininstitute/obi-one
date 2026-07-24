# `efeature_extraction` — exposed parameters

This stage extracts experimental e-features from ephys traces by running
BluePyEModel's `extract_save_features_protocols` (which wraps `bluepyefe.extract`
and eFEL). Its tunable parameters are surfaced across four blocks:

| Block | UI element | Scope |
|---|---|---|
| `Settings` (`blocks/settings.py`) | `block_single` | Global eFEL settings + bluepyefe/BluePyEModel extraction-flow knobs |
| `RheobaseStrategy` union (`blocks/rheobase.py`) | `block_union` | Rheobase algorithm + its parameters (one block per strategy) |
| `Protocol` (`protocols_and_features/protocols.py`) | — | Per-protocol eFEL overrides |
| `EFeature` (`protocols_and_features/efeatures.py`) | — | Per-feature target settings + eFEL overrides |

**eFEL override cascade:** `Settings` (global) → `Protocol` → `EFeature`. The
most specific level that sets a value wins; unset (`None`) inherits upward.

Not every bluepyefe/eFEL parameter is exposed. This file records what is left in,
what is left out, and why. The eFEL keep/omit decision was made by tracing each
eFEL setting to the feature(s) that read it (eFEL C++ sources + `pyfeatures` +
`DependencyV5.txt`) and keeping only those that touch a feature this stage can
extract — directly or as a dependency. The feature catalogue is the set of
`EFeature` subclasses in `protocols_and_features/efeatures.py`.

---

## Global eFEL settings (`Settings`)

### Left in (16) — affect an extractable feature

| `Settings` field | eFEL key | Drives (catalogue feature / role) |
|---|---|---|
| `threshold` | `Threshold` | spike detection → every spike-based feature |
| `derivative_threshold` | `DerivativeThreshold` | `AP_begin_indices` → AP_amplitude, AP_begin_voltage, AP_begin_width, AP_duration_half_width |
| `down_derivative_threshold` | `DownDerivativeThreshold` | `AP_end_indices` → AP_duration_half_width |
| `derivative_window` | `DerivativeWindow` | `AP_begin_indices` (same chain as `DerivativeThreshold`) |
| `interp_step` | `interp_step` | trace resampling → universal dependency of all features |
| `strict_stiminterval` | `strict_stiminterval` | spike / min-AHP windowing |
| `spike_skipf` | `spike_skipf` | adaptation_index |
| `max_spike_skip` | `max_spike_skip` | adaptation_index |
| `ignore_first_isi` | `ignore_first_ISI` | ISI_CV, ISI_log_slope, irregularity_index, strict-burst features |
| `strict_burst_factor` | `strict_burst_factor` | strict_burst_number, strict_burst_mean_freq |
| `initial_perc` | `initial_perc` | number_initial_spikes |
| `voltage_base_start_perc` | `voltage_base_start_perc` | voltage_base (+ deps: AHP_depth, sag_ratio*, ohmic_input_resistance_vb_ssse) |
| `voltage_base_end_perc` | `voltage_base_end_perc` | voltage_base (+ deps) |
| `voltage_base_mode` | `voltage_base_mode` | voltage_base (+ deps) |
| `depol_block_min_duration` | `depol_block_min_duration` | depol_block_bool |
| `precision_threshold` | `precision_threshold` | voltage_base numerical tolerance |

### Left out (14) — only drive features this stage cannot extract

| eFEL key | Only drives | Reason omitted |
|---|---|---|
| `min_spike_height` | — | Orphan: read by no feature in the installed eFEL build (empirically confirmed — 20 vs 500 leaves Spikecount unchanged) |
| `burst_factor` | burst_number, burst_mean_freq, interburst_voltage | non-catalogue (catalogue uses *strict* burst features → `strict_burst_factor`) |
| `initburst_freq_threshold` | initburst_sahp* | non-catalogue (`number_initial_spikes` uses `initial_perc`, not this) |
| `initburst_sahp_start` | initburst_sahp* | non-catalogue |
| `initburst_sahp_end` | initburst_sahp* | non-catalogue |
| `current_base_start_perc` | current_base → impedance | non-catalogue |
| `current_base_end_perc` | current_base → impedance | non-catalogue |
| `current_base_mode` | current_base → impedance | non-catalogue |
| `rise_start_perc` | AP_rise_time / AP_rise_rate | non-catalogue |
| `rise_end_perc` | AP_rise_time / AP_rise_rate | non-catalogue |
| `sahp_start` | postburst_slow_ahp_indices, AHP_depth_abs_slow | non-catalogue |
| `impedance_max_freq` | impedance | non-catalogue |
| `AP_phaseslope_range` | AP_phaseslope | non-catalogue |
| `inactivation_tc_end_skip` | inactivation_time_constant | non-catalogue |

> If the feature catalogue grows (new `EFeature` subclasses), revisit this list —
> a setting omitted here may become relevant.

---

## Extraction-flow knobs (`Settings`)

These map onto `bluepyefe.extract` arguments / `EModelPipelineSettings` fields
that `extract_save_features_protocols` forwards (set in
`task._build_extraction_recipes`).

### Left in

| `Settings` field | recipe `pipeline_settings` key |
|---|---|
| `plot_extraction` | `plot_extraction` |
| `default_std_value` | `default_std_value` |
| `threshold_nvalue_save` | `extraction_threshold_value_save` |
| `pickle_cells` | `pickle_cells_extraction` |
| `bound_max_std` | `bound_max_std` |
| `interpolate_rmp` | `interpolate_RMP_extraction` |
| `threshold_efeature_std` | `threshold_efeature_std` |
| `minimum_protocol_delay` | `minimum_protocol_delay` |
| `name_rin_protocol` | `name_Rin_protocol` |
| `name_rmp_protocol` | `name_rmp_protocol` |

### Left out

| Parameter | Reason omitted |
|---|---|
| `protocol_mode` | `extract_save_features_protocols` does not forward it → no-op |
| `low_memory_mode` | not forwarded → no-op |
| `extract_per_cell` | not forwarded → no-op |
| `extraction_reader` | custom reader callable; readers are auto-detected from the NWB |
| `extract_absolute_amplitudes` | hardcoded `True` — amplitudes are read from the NWB in absolute nA, so relative (%-rheobase) mode would mismatch |
| `rheobase_strategy` / `rheobase_settings` | moved into the `RheobaseStrategy` block (below) |
| `protocols_rheobase` | moved into the `RheobaseStrategy` block (`protocols` field) |

> With `extract_absolute_amplitudes=True`, BluePyEModel nulls
> `name_rmp_protocol`/`name_Rin_protocol` (with a warning); they default to
> `None`, so the common case is unaffected.

---

## Rheobase (`RheobaseStrategy` block union)

`block_union` — the user picks one strategy block, which shows only its own
parameters. `protocols` (the rheobase protocols) is shared by all strategies.
`to_dict()` emits exactly the kwargs the chosen `bluepyefe.rheobase` function
accepts → forwarded as `rheobase_settings_extraction`; the block's `strategy`
name → `rheobase_strategy_extraction`.

| Strategy block | `strategy` | Parameters |
|---|---|---|
| `AbsoluteRheobase` (default) | `absolute` | `spike_threshold` |
| `FlushRheobase` | `flush` | `flush_length`, `upper_bound_spikecount` |
| `MajorityRheobase` | `majority` | `min_step`, `majority` |
| `InterpolationRheobase` | `interpolation` | *(none)* |

Shared by all: `protocols` (protocols whose recordings drive the rheobase search).

---

## Per-protocol overrides (`Protocol`)

Always-present eFEL settings (default to eFEL's own defaults; override the
global `Settings` value, overridden in turn by a feature that sets the same
field):

`spike_detection_threshold` (`Threshold`, default -20.0) and `interp_step` (default 0.025).
`strict_stiminterval` is fixed to True in the emitted eFEL settings and is not
exposed as a per-level knob.

Additional eFEL settings can be added via `custom_efel_settings` (a dict of
key-value pairs using eFEL's native setting names).

User-editable stimulus timing (None = auto-detect from NWB):

`ton`, `toff`, `tmid`, `tmid2`.

---

## Per-feature settings (`EFeature`)

Structural target fields plus per-feature eFEL settings (always-present with
eFEL defaults, overridden in turn by `custom_efel_settings`):

| Field | Role |
|---|---|
| `extract` | on/off — whether this feature is sent to bluepyefe at all |
| `weight` | fitness weight (bluepyefe `Target.weight`) |
| `tolerance` | amplitude tolerance for matching recordings |
| `spike_detection_threshold` | eFEL `Threshold` (feature override; None = inherit) |
| `interp_step` | eFEL `interp_step` (default 0.025) |
| `stim_start` | eFEL `stim_start` — per-feature stimulus onset (ms), overrides the protocol |
| `stim_end` | eFEL `stim_end` — per-feature stimulus end (ms), overrides the protocol |
| `custom_efel_settings` | additional eFEL settings as a key-value dict |

`efel_name` is a ClassVar fixed by each concrete subclass, not an editable
field. The frontend deep-links a feature's documentation by appending
`#<efel_name>` to the block's `SchemaKey.EFEL_DOC_BASE_URL`. Subclasses that
have an illustrative figure in the eFEL docs name it via
`SchemaKey.EFEL_FEATURE_IMAGE`, resolved against the block's
`SchemaKey.EFEL_FIGURES_BASE_URL`.

---

## Read from the NWB (auto-detected when not user-specified)

These per-protocol/per-recording values are read from each
`ElectricalCellRecording`'s NWB asset at execution time. The timing fields
(`ton`, `toff`, `tmid`, `tmid2`) can be overridden by the user on the
`Protocol` class; when left `None`, they are auto-detected from the NWB.

- **Stimulus timing:** `ton`, `toff`, `tmid`, `tmid2`, `tend`, `t1`–`t4`
- **Amplitudes:** `amp`, `hypamp`, `amp2` (discovered per protocol, in nA)
- **Units / sampling:** `i_unit`, `v_unit`, `t_unit`, `dt`
- **Liquid junction potential:** `ljp` (read from the `ElectricalCellRecording` entity)

## eFEL doc figures with no model class (47)

`EFeature` subclasses exist only for features some protocol can actually
extract — the 32 named in the per-protocol feature sets mirrored from
[BluePyEfe PR #23](https://github.com/openbraininstitute/BluePyEfe/pull/23). Of
those, 18 have an illustrative figure in the eFEL docs, named on the class via
`SchemaKey.EFEL_FEATURE_IMAGE` and resolved by the frontend against
`SchemaKey.EFEL_FIGURES_BASE_URL`.

The eFEL docs illustrate a wider set than we model. The 47 features below share
one of those same figures but have **no** `EFeature` subclass, because no
protocol lists them as extractable. They are recorded here as the candidate set
should a protocol's feature list ever widen: adding one means adding an
`EFeature` subclass in `protocols_and_features/efeatures.py` and putting it in
the relevant per-protocol union.

Grouped by the figure they share:

**`AHP.png`**

- `AHP_depth_abs`
- `AHP_depth_diff`
- `AHP_depth_from_peak`
- `AHP1_depth_from_peak`
- `AHP2_depth_from_peak`
- `fast_AHP`
- `fast_AHP_change`
- `AHP_depth_abs_slow`
- `AHP_depth_slow`
- `AHP_slow_time`
- `min_AHP_indices`
- `min_AHP_values`

**`AP_Amplitude.png`**

- `AP2_amp`
- `APlast_amp`
- `mean_AP_amplitude`
- `AP_amplitude_change`
- `AP_amplitude_from_voltagebase`
- `AP_height`
- `AP1_peak`
- `AP2_peak`
- `peak_voltage`

**`AP_duration_half_width.png`**

- `AP_duration_half_width_change`
- `AP_width`
- `AP_duration`
- `AP_duration_change`
- `spike_half_width`
- `AP1_width`
- `AP2_width`
- `APlast_width`
- `AP_rise_time`
- `AP_fall_time`

**`inv_ISI.png`**

- `ISI_values`
- `all_ISI_values`
- `inv_ISI_values`
- `inv_fourth_ISI`
- `inv_fifth_ISI`
- `ISI_semilog_slope`
- `ISI_log_slope_skip`

**`sag.png`**

- `sag_time_constant`

**`voltage_features.png`**

- `steady_state_voltage_stimend`
- `steady_state_voltage`
- `voltage_deflection`
- `voltage_deflection_vb_ssse`
- `voltage_deflection_begin`
- `minimum_voltage`
- `maximum_voltage`
- `ohmic_input_resistance`
