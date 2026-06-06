"""Blocks for the 01_efeature_extraction stage.

The extraction stage runs ``bluepyefe.extract.extract_efeatures`` directly on
the experimental traces, so the only required input is one or more
:class:`~obi_one.scientific.from_id.electrical_cell_recording_from_id.ElectricalCellRecordingFromID`
entities — model assets (recipes, morphologies, mechanisms, params) all belong
to the optimisation stage. The remaining blocks expose the bluepyefe parameters
that influence experimental e-feature extraction.
"""

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)


class ExtractionInitialize(Block):
    """Filesystem inputs for the extraction stage.

    The extraction stage runs ``bluepyefe.extract.extract_efeatures`` directly on
    the experimental traces — no model metadata, recipes, morphologies, or
    mechanisms are needed here. Those belong to the optimisation stage.
    """

    # Tuple instead of list so the framework doesn't expand it as a scan dimension.
    electrical_cell_recording: tuple[ElectricalCellRecordingFromID, ...] = Field(
        title="Electrical cell recordings",
        description=(
            "ElectricalCellRecording entities to extract features from (>= 1)."
            " Each entity's NWB asset is downloaded into the working directory's"
            " ``ephys_data/`` folder."
        ),
        min_length=1,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE,
        },
    )


class Settings(Block):
    """Combined eFEL and ``bluepyefe.extract`` settings for the extraction stage."""

    # ``efel_settings`` block of ``pipeline_settings``.
    threshold: float | list[float] = Field(
        default=-20.0,
        title="Spike threshold",
        description="Voltage threshold used by eFEL for spike detection.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    interp_step: PositiveFloat | list[PositiveFloat] = Field(
        default=0.025,
        title="Interpolation step",
        description="eFEL interpolation step.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    strict_stiminterval: bool = Field(
        default=True,
        title="Strict stim interval",
        description="Forward to eFEL's ``strict_stiminterval`` flag.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    # Top-level parameters forwarded to ``bluepyefe.extract.extract_efeatures``.
    plot_extraction: bool = Field(
        default=True,
        title="Plot extraction",
        description="Whether to render extraction figures alongside the JSON output.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    default_std_value: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Default std value",
        description="Replaces zero standard deviations during feature extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    extract_absolute_amplitudes: bool = Field(
        default=False,
        title="Extract absolute amplitudes",
        description="Whether to extract absolute (vs. rheobase-relative) amplitudes.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    protocols_rheobase: tuple[str, ...] = Field(
        default=("IDthresh",),
        title="Rheobase protocols",
        description="Protocols used to determine the rheobase.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    name_rin_protocol: str | None = Field(
        default=None,
        title="Rin protocol name",
        description=(
            "Protocol used to compute input resistance (e.g. ``IV_-20``). Leave"
            " ``None`` to skip; set when the requested protocol is present in the"
            " recordings being extracted."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rmp_protocol: str | None = Field(
        default=None,
        title="RMP protocol name",
        description=(
            "Protocol used to compute resting membrane potential (e.g. ``IV_0``)."
            " Leave ``None`` to skip; set when the requested protocol is present"
            " in the recordings being extracted."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    def efel_to_dict(self) -> dict:
        return {
            "Threshold": self.threshold,
            "interp_step": self.interp_step,
            "strict_stiminterval": self.strict_stiminterval,
        }


# Catalogue of eFEL features typically extracted per BluePyEModel protocol type.
# Mirrors the L5PC example's ``targets.py`` and the ``AUTO_TARGET_DICT`` presets
# in ``bluepyemodel/efeatures_extraction/auto_targets.py``. Exposed to the
# frontend via the ``available_efeatures_by_protocol`` key of the
# ``select_efeatures_by_protocol`` UI element so it can render a feature picker
# for whichever protocols the
# ``/declared/electrical-cell-recording-protocols`` endpoint returns.
EFEATURE_CATALOGUE_BY_PROTOCOL: dict[str, tuple[str, ...]] = {
    "IDrest": (
        "Spikecount",
        "depol_block_bool",
        "voltage_base",
        "voltage_after_stim",
        "mean_frequency",
        "time_to_first_spike",
        "time_to_last_spike",
        "inv_time_to_first_spike",
        "inv_first_ISI",
        "inv_second_ISI",
        "inv_third_ISI",
        "inv_last_ISI",
        "ISI_CV",
        "ISI_log_slope",
        "doublet_ISI",
        "AHP_depth",
        "AHP_time_from_peak",
        "min_AHP_values",
        "strict_burst_number",
        "strict_burst_mean_freq",
        "number_initial_spikes",
        "irregularity_index",
        "adaptation_index",
    ),
    "IDthresh": (
        "Spikecount",
        "mean_frequency",
        "voltage_base",
        "voltage_after_stim",
        "AHP_depth",
    ),
    "IV": (
        "voltage_base",
        "ohmic_input_resistance_vb_ssse",
        "sag_amplitude",
        "sag_ratio1",
        "sag_ratio2",
        "decay_time_constant_after_stim",
    ),
    "APWaveform": (
        "AP_amplitude",
        "AP1_amp",
        "AP_duration_half_width",
        "AHP_depth",
        "AP_begin_voltage",
        "AP_begin_width",
    ),
    "sAHP": (
        "mean_frequency",
        "voltage_base",
        "depol_block_bool",
        "AHP_depth",
        "AHP_time_from_peak",
    ),
    "IDhyperpol": (
        "mean_frequency",
        "voltage_base",
        "depol_block_bool",
    ),
}


class EFeatureParams(OBIBaseModel):
    """Per-feature tuning parameters inside a :class:`ProtocolSelection`."""

    weight: PositiveFloat = Field(
        default=1.0,
        title="Weight",
        description=(
            "Relative weight of this efeature in the fitness function (passed to"
            " ``bluepyefe``'s Target ``weight`` parameter)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    tolerance: PositiveFloat = Field(
        default=20.0,
        title="Tolerance",
        description=(
            "Amplitude tolerance (in % of rheobase, or pA when"
            " ``extract_absolute_amplitudes=True``) used to match recordings to"
            " the requested target amplitude."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )


class ProtocolSelection(OBIBaseModel):
    """Per-protocol timing, amplitudes, and selected efeatures.

    Combines the timing metadata that used to live in ``ECodeMetadata`` with the
    amplitudes/efeatures that used to live in ``ProtocolTarget``. The liquid
    junction potential (``ljp``) is still read from each
    ``ElectricalCellRecording`` entity at run time and merged into the ecode
    metadata, so it isn't exposed here.
    """

    ton: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="ton",
        description="Stimulus onset (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    toff: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="toff",
        description="Stimulus offset (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    tmid: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="tmid",
        description="Optional midpoint timing (ms) (used by sAHP and similar protocols).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    tmid2: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="tmid2",
        description="Optional second midpoint timing (ms).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    amplitudes: tuple[float, ...] = Field(
        default=(),
        title="Amplitudes",
        description="Amplitudes (in pA) to extract features at.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    efeatures: dict[str, EFeatureParams] = Field(
        default_factory=dict,
        title="E-features",
        description=(
            "Selected eFEL features for this protocol, keyed by feature name,"
            " each with per-feature ``weight`` / ``tolerance`` overrides."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY},
    )

    def ecode_metadata_dict(self) -> dict:
        d: dict[str, float] = {}
        for key in ("ton", "toff", "tmid", "tmid2"):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        return d


def _default_protocol_selection() -> dict[str, ProtocolSelection]:
    """L5PC-style defaults merged from the old ``ecodes_metadata`` + ``targets``."""

    def _features(*names: str) -> dict[str, EFeatureParams]:
        return {name: EFeatureParams() for name in names}

    return {
        "IDthresh": ProtocolSelection(),
        "IDrest": ProtocolSelection(
            amplitudes=(150, 250),
            efeatures=_features(
                "Spikecount",
                "mean_frequency",
                "time_to_first_spike",
                "time_to_last_spike",
                "inv_time_to_first_spike",
                "inv_first_ISI",
                "inv_second_ISI",
                "inv_third_ISI",
                "inv_last_ISI",
                "AHP_depth",
                "AHP_time_from_peak",
                "min_AHP_values",
                "depol_block_bool",
                "voltage_base",
            ),
        ),
        "IV": ProtocolSelection(
            amplitudes=(0, -20, -100),
            efeatures=_features("voltage_base", "ohmic_input_resistance_vb_ssse"),
        ),
        "APWaveform": ProtocolSelection(
            amplitudes=(280,),
            efeatures=_features(
                "AP_amplitude",
                "AP1_amp",
                "AP_duration_half_width",
                "AHP_depth",
            ),
        ),
        "sAHP": ProtocolSelection(
            amplitudes=(220,),
            efeatures=_features("mean_frequency", "voltage_base", "depol_block_bool"),
        ),
    }


class SelectEFeaturesByProtocol(Block):
    """Per-protocol picker for timing, amplitudes, and chosen efeatures.

    Each entry in ``selected`` carries the protocol's ``ecodes_metadata`` timing
    fields, the amplitudes at which to extract features, and the user-selected
    subset of eFEL features (with per-feature weight/tolerance). The catalogue
    of features known per protocol is hardcoded in
    :data:`EFEATURE_CATALOGUE_BY_PROTOCOL` and advertised to the frontend via
    the ``available_efeatures_by_protocol`` key on the field's
    ``json_schema_extra``.
    """

    selected: dict[str, ProtocolSelection] = Field(
        default_factory=_default_protocol_selection,
        title="EFeatures by protocol",
        description=(
            "Per-protocol timing, amplitudes, and selected eFEL features."
            " Defaults mirror the L5PC example; the frontend can repopulate"
            " this from the catalogue and the protocols returned by"
            " ``/declared/electrical-cell-recording-protocols``."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            "available_efeatures_by_protocol": {
                protocol: list(features)
                for protocol, features in EFEATURE_CATALOGUE_BY_PROTOCOL.items()
            },
        },
    )
