# Recording summary

Each `ElectricalCellRecording` can carry a `recording_summary` asset: one JSON file with,
for each protocol in its NWB file, the distinct current amplitudes and stimulus times,
and the cell's rheobase per step protocol. Everything before e-feature extraction (the
UI, the config, the extraction task's preparation) reads this file instead of the NWB
file. entitycore stores the file without validating it; obi-one owns the format,
defined by [`recording-summary.schema.json`](recording-summary.schema.json) and the
`RecordingSummary` model in `obi_one/scientific/library/recording_summary.py`.

## Example

```json
{
  "version": 1,
  "units": { "current": "nA", "time": "ms" },
  "protocols": {
    "IDThreshold": { "amp": [0.05, 0.06, 0.07], "ton": [700.25], "toff": [2700.25] },
    "IDRest":      { "amp": [0.15, 0.25], "ton": [520.25, 700.25], "toff": [720.25, 2700.25] },
    "IV":          { "amp": [-0.14, -0.066, 0.0], "ton": [20.25], "toff": [1020.25] },
    "sAHP":        { "amp": [0.106, 0.144], "long_amp": [0.053], "ton": [20.5], "tmid": [520.5], "tmid2": [720.5], "toff": [2720.5] },
    "APThreshold": { "amp": [0.3], "ton": [20.8] }
  },
  "rheobase": { "IDThreshold": 0.05, "IDRest": 0.15, "IV": null }
}
```

## Fields

- **`protocols`**: keyed by protocol name as written in the NWB file. Only current-clamp
  stimuli are included: a stimulus series typed `CurrentClampStimulusSeries`, or, when the
  file does not type it, one whose unit is a current unit.
- **Amplitudes**: distinct values in nA relative to the holding current, across all sweeps
  and repetitions, sorted and rounded to 0.001 nA. The lists are not paired sweep by sweep.
  The keys are those bluepyefe writes to `extracted_features.json` and BluePyEModel's
  stimuli take, so `amp` is always the amplitude extraction targets are matched on:

  | eCode | `amp` | other step |
  |---|---|---|
  | Step (IDrest, IDthresh, IV, APWaveform, …) | step | — |
  | sAHP family (sAHP, IDhyperpol, IRhyperpol, IDdepol, IRdepol) | short step | `long_amp` |
  | HyperDePol | first, hyperpolarising step | `amp2` (depolarising) |
  | DeHyperPol | first, depolarising step | `amp2` (hyperpolarising) |
  | Ramp, posCheops, sineSpec | peak | — |
  | negCheops | trough | — |
  | pinkNoise, capCheck | largest absolute deviation | — |
  | SpikeRec | not stored (matched on spike interval) | — |

- **Timing** (`ton`, `tmid`, `tmid2`, `toff`): the stimulus times, in ms from the start of
  the sweep, with the names bluepyefe reads from its files metadata. They are detected on
  each sweep and stored as distinct values (rounded to 0.01 ms; values within 2 ms count
  once). Several values mean the protocol's sweeps differ, e.g. `IDRest` above.

  | eCode | keys |
  |---|---|
  | Step | `ton`, `toff` |
  | sAHP family | `ton`, `tmid` (start of the short step), `tmid2` (its end), `toff` |
  | HyperDePol, DeHyperPol | `ton`, `tmid` (start of the second step), `toff` |
  | Ramp | `ton` (bluepyefe takes the end at the current maximum) |
  | others | not stored: left to bluepyefe |

  A step edge is where the mean current over the next 5 ms differs from the mean over the
  previous 5 ms by more than 8 noise standard deviations; the noise comes from the
  sample-to-sample differences, so the steps themselves do not inflate it. bluepyefe's
  own detection estimates the noise from the first 50 samples and the rest current from
  the first 300. In files with a short rest before the stimulus (e.g. 20 ms at 0.5 ms
  sampling) both overlap the step, and bluepyefe then misreads it. A sweep whose shape
  does not match its eCode (e.g. no step at 0 nA) gives no timing. A ramp's onset is the
  start of its rise, fitted with a line, extrapolated back to the rest current.
- **`rheobase`**: for each step protocol (Step eCode, except spontaneous and hold
  protocols), the smallest amplitude whose sweep fires at least one spike, from that
  protocol's sweeps alone. It is computed by bluepyefe (`absolute` strategy, eFEL
  `Threshold` −20 mV, `strict_stiminterval`) on the sweeps read with the stored timing,
  as extraction reads them. `null` when no sweep fires. A value of 0 or below means a
  sweep fires without current injected: bluepyefe then drops the cell from relative
  extraction.

  With several rheobase protocols, bluepyefe takes the smallest of their rheobases; a
  recording is usable when that smallest value is positive
  (`RecordingSummary.rheobase_for`).

## Computing and storing it

```python
from obi_one.db_sdk.registration.electrical_cell_recording import upload_recording_summary
from obi_one.scientific.library.recording_summary import compute_recording_summary

summary = compute_recording_summary(nwb_path)
upload_recording_summary(client, recording_id, summary)  # admin=True for public recordings
```

- `compute_recording_summary` only reads the local NWB file. It also reads each timed
  protocol once with bluepyefe, using the detected timing, and logs a warning when a sweep
  amplitude bluepyefe reads is not among the stored ones, so a wrong summary is not stored
  silently.
- `upload_recording_summary` replaces any existing summary of the recording. Run it at
  ingest, or in a backfill over existing recordings.
- `GET /declared/electrical-cell-recording-summary?recording_id=…` computes the summary of
  a recording from its NWB file and returns it, without storing it.
- `GET /declared/mapped-electrical-cell-recording-properties` reads each recording's
  stored summary; for a recording without one, it computes the summary from the NWB file
  on every request.
- The e-feature extraction task reads each recording's summary, and computes it from the
  downloaded NWB file when there is none.
- Uploading needs entitysdk 0.19.35 or later; older versions fail to load a recording that
  has a `recording_summary` asset.
