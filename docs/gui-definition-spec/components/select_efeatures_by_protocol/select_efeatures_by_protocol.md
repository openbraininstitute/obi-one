## select_efeatures_by_protocol

ui_element: `select_efeatures_by_protocol`

Backs [`SelectEFeaturesByProtocol`](../../../../obi_one/scientific/tasks/emodel_optimization/_01_efeature_extraction/blocks.py) — a single object that lets the user pick which eFEL features to extract for each ephys protocol, with editable per-feature parameters.

The schema advertises the **catalogue of features known per protocol** under the
`available_efeatures_by_protocol` extra. The frontend filters this catalogue to
the protocols returned by the
[`/declared/electrical-cell-recording-protocols`](../../../../app/endpoints/electrical_cell_recording_properties.py)
endpoint (one row per protocol — see screenshot), and the user activates a
subset of the listed features. For each activated feature the user can edit
`weight` and `tolerance`; the persisted value is the dict of selected features
only.

- The block field's `type` must be `"object"`.
- It must expose an `available_efeatures_by_protocol` extra: a non-empty
  dictionary mapping protocol name (string) → list of efeature name strings.
- The catalogue ships baked-in for the L5PC-style BluePyEModel protocols
  (`IDrest`, `IDthresh`, `IV`, `APWaveform`, `sAHP`, `IDhyperpol`), derived from
  the `AUTO_TARGET_DICT` presets in
  [`bluepyemodel.efeatures_extraction.auto_targets`](https://github.com/openbraininstitute/BluePyEModel/blob/main/bluepyemodel/efeatures_extraction/auto_targets.py).

### Example Pydantic implementation

```py
class EFeatureParams(Block):
    weight: PositiveFloat = Field(default=1.0, ...)
    tolerance: PositiveFloat = Field(default=20.0, ...)


class SelectEFeaturesByProtocol(Block):
    selected: dict[str, dict[str, EFeatureParams]] = Field(
        default_factory=dict,
        title="EFeatures by protocol",
        description="...",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            "available_efeatures_by_protocol": {
                "IDrest": ["Spikecount", "mean_frequency", ...],
                "IV": ["voltage_base", "ohmic_input_resistance_vb_ssse", ...],
                "APWaveform": ["AP_amplitude", "AHP_depth", ...],
                ...
            },
        },
    )
```

### Persisted shape

```jsonc
{
  "selected": {
    "IDrest": {
      "AHP_depth":   { "weight": 1.0, "tolerance": 20.0 },
      "AP_amplitude": { "weight": 1.0, "tolerance": 20.0 }
    },
    "APWaveform": {
      "AHP_depth":   { "weight": 1.0, "tolerance": 20.0 }
    }
  }
}
```

Protocols / features the user did not activate are simply absent from the dict —
no need to send the full catalogue back.

### User flow

1. Frontend calls `/declared/electrical-cell-recording-protocols` with the
   selected `ElectricalCellRecording` ids; takes the `union` of protocol names.
2. Frontend intersects that union with the protocol keys in
   `available_efeatures_by_protocol` to decide which protocol boxes to render.
3. Each protocol box lists its catalogue features with a checkbox + per-feature
   settings icon.
4. Checking a feature inserts it into `selected[protocol][feature]` with the
   default `weight` / `tolerance`; the settings icon opens editors for those
   values.

### UI design

<img src="design/select_efeatures_by_protocol.png" width="600" />
