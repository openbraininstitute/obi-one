"""eFEL feature Pydantic models with per-feature tunable parameters.

Each feature is a Pydantic subclass of :class:`EFeature` carrying its own
tunable parameters (``weight``, ``tolerance``, per-feature eFEL setting
overrides) and an ``extract`` flag toggling whether the feature is included
in the extraction. Protocols (in :mod:`.protocols`) expose each valid feature
as a typed field; the flag is what differentiates ``IDrest.spikecount`` between
"present in the schema" and "send to bluepyefe".
"""

from typing import ClassVar

from pydantic import Field, PositiveFloat

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class EFeature(OBIBaseModel):
    """Base class for tunable bluepyefe e-features.

    Subclasses declare ``efel_name`` (the eFEL feature key used in bluepyefe
    target rows) and ``category`` (grouping for the UI's "add feature" modal).

    Fields mirror the per-target tunable parameters of
    ``bluepyefe.target.EFeatureTarget``: ``tolerance`` and ``efel_settings``
    overrides. ``weight`` is forwarded downstream to the fitness-calculator
    configuration. ``extract`` is the on/off switch consumed by
    ``Protocol.selected_efeatures``.

    The three always-present eFEL settings (``Threshold``,
    ``strict_stiminterval``, ``interp_step``) default to eFEL's own defaults
    and are always emitted in ``efel_settings_override()``. Two additional
    optional fields (``stim_start``, ``stim_end``) are emitted only when set.
    Further eFEL settings can be added via ``custom_efel_settings``.
    """

    efel_name: ClassVar[str]
    efel_doc_url: ClassVar[str] = "https://efel.readthedocs.io/en/latest/eFeatures.html"
    category: ClassVar[str] = "Spike event"

    json_schema_extra_additions: ClassVar[dict] = {
        "efel_doc_url": "https://efel.readthedocs.io/en/latest/eFeatures.html",
    }

    extract: bool = Field(
        default=False,
        title="Extract",
        description="Whether to include this efeature in the bluepyefe extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
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
    efeature_name: str | None = Field(
        default=None,
        title="Feature name",
        description=(
            "Custom name for this target (bluepyefe ``efeature_name``). Lets the"
            " same eFEL feature be extracted under a distinct label, e.g."
            " ``Spikecount_phase1``. Leave ``None`` to use the eFEL feature name."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    # ------------------------------------------------------------------
    # Always-present eFEL settings with eFEL defaults pre-filled
    # ------------------------------------------------------------------
    threshold: float = Field(
        default=-20.0,
        title="Threshold",
        description="eFEL ``Threshold``: voltage above which a spike is detected (mV).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    strict_stiminterval: bool = Field(
        default=True,
        title="Strict stim interval",
        description=(
            "eFEL ``strict_stiminterval``: only count spikes strictly within"
            " [stim_start, stim_end]."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interp_step: PositiveFloat = Field(
        default=0.025,
        title="Interpolation step",
        description=(
            "eFEL ``interp_step``: time step the trace is resampled to before"
            " extraction (ms)."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # ------------------------------------------------------------------
    # Optional per-feature stimulus window overrides
    # ------------------------------------------------------------------
    stim_start: float | None = Field(
        default=None,
        title="Stim start",
        description=(
            "eFEL ``stim_start``: stimulus onset time for this feature (ms)."
            " Overrides the protocol-level value. Leave empty to use the"
            " protocol's detected onset."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    stim_end: float | None = Field(
        default=None,
        title="Stim end",
        description=(
            "eFEL ``stim_end``: stimulus end time for this feature (ms)."
            " Overrides the protocol-level value. Leave empty to use the"
            " protocol's detected end."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # ------------------------------------------------------------------
    # Additional eFEL settings (picker)
    # ------------------------------------------------------------------
    custom_efel_settings: dict[str, float | bool] | None = Field(
        default=None,
        title="Custom eFEL settings",
        description=(
            "Additional eFEL settings beyond the always-present Threshold,"
            " strict_stiminterval, and interp_step. Keys are eFEL setting names."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY},
    )

    def efel_settings_override(self) -> dict:
        """Build the per-feature ``efel_settings`` overrides for this target row.

        The 3 always-present settings are always emitted. ``stim_start`` and
        ``stim_end`` are emitted only when not None. Additional settings from
        ``custom_efel_settings`` are merged on top. Each setting overrides the
        protocol- and global-level eFEL setting for this feature.
        """
        overrides: dict[str, float | bool] = {
            "Threshold": self.threshold,
            "strict_stiminterval": self.strict_stiminterval,
            "interp_step": self.interp_step,
        }
        if self.stim_start is not None:
            overrides["stim_start"] = self.stim_start
        if self.stim_end is not None:
            overrides["stim_end"] = self.stim_end
        if self.custom_efel_settings:
            overrides.update(self.custom_efel_settings)
        return overrides


# ---------------------------------------------------------------------------
# Spike event features
# ---------------------------------------------------------------------------


class Spikecount(EFeature):
    efel_name: ClassVar[str] = "Spikecount"
    category: ClassVar[str] = "Spike event"


class MeanFrequency(EFeature):
    efel_name: ClassVar[str] = "mean_frequency"
    category: ClassVar[str] = "Spike event"


class TimeToFirstSpike(EFeature):
    efel_name: ClassVar[str] = "time_to_first_spike"
    category: ClassVar[str] = "Spike event"


class TimeToLastSpike(EFeature):
    efel_name: ClassVar[str] = "time_to_last_spike"
    category: ClassVar[str] = "Spike event"


class InvTimeToFirstSpike(EFeature):
    efel_name: ClassVar[str] = "inv_time_to_first_spike"
    category: ClassVar[str] = "Spike event"


class InvFirstISI(EFeature):
    efel_name: ClassVar[str] = "inv_first_ISI"
    category: ClassVar[str] = "Spike event"


class InvSecondISI(EFeature):
    efel_name: ClassVar[str] = "inv_second_ISI"
    category: ClassVar[str] = "Spike event"


class InvThirdISI(EFeature):
    efel_name: ClassVar[str] = "inv_third_ISI"
    category: ClassVar[str] = "Spike event"


class InvLastISI(EFeature):
    efel_name: ClassVar[str] = "inv_last_ISI"
    category: ClassVar[str] = "Spike event"


class ISICV(EFeature):
    efel_name: ClassVar[str] = "ISI_CV"
    category: ClassVar[str] = "Spike event"


class ISILogSlope(EFeature):
    efel_name: ClassVar[str] = "ISI_log_slope"
    category: ClassVar[str] = "Spike event"


class DoubletISI(EFeature):
    efel_name: ClassVar[str] = "doublet_ISI"
    category: ClassVar[str] = "Spike event"


class StrictBurstNumber(EFeature):
    efel_name: ClassVar[str] = "strict_burst_number"
    category: ClassVar[str] = "Spike event"


class StrictBurstMeanFreq(EFeature):
    efel_name: ClassVar[str] = "strict_burst_mean_freq"
    category: ClassVar[str] = "Spike event"


class NumberInitialSpikes(EFeature):
    efel_name: ClassVar[str] = "number_initial_spikes"
    category: ClassVar[str] = "Spike event"


class IrregularityIndex(EFeature):
    efel_name: ClassVar[str] = "irregularity_index"
    category: ClassVar[str] = "Spike event"


class AdaptationIndex(EFeature):
    efel_name: ClassVar[str] = "adaptation_index"
    category: ClassVar[str] = "Spike event"


# ---------------------------------------------------------------------------
# Spike shape features
# ---------------------------------------------------------------------------


class APAmplitude(EFeature):
    efel_name: ClassVar[str] = "AP_amplitude"
    category: ClassVar[str] = "Spike shape"


class AP1Amp(EFeature):
    efel_name: ClassVar[str] = "AP1_amp"
    category: ClassVar[str] = "Spike shape"


class APDurationHalfWidth(EFeature):
    efel_name: ClassVar[str] = "AP_duration_half_width"
    category: ClassVar[str] = "Spike shape"


class APBeginVoltage(EFeature):
    efel_name: ClassVar[str] = "AP_begin_voltage"
    category: ClassVar[str] = "Spike shape"


class APBeginWidth(EFeature):
    efel_name: ClassVar[str] = "AP_begin_width"
    category: ClassVar[str] = "Spike shape"


class AHPDepth(EFeature):
    efel_name: ClassVar[str] = "AHP_depth"
    category: ClassVar[str] = "Spike shape"


class AHPTimeFromPeak(EFeature):
    efel_name: ClassVar[str] = "AHP_time_from_peak"
    category: ClassVar[str] = "Spike shape"


class MinAHPValues(EFeature):
    efel_name: ClassVar[str] = "min_AHP_values"
    category: ClassVar[str] = "Spike shape"


# ---------------------------------------------------------------------------
# Subthreshold features
# ---------------------------------------------------------------------------


class VoltageBase(EFeature):
    efel_name: ClassVar[str] = "voltage_base"
    category: ClassVar[str] = "Subthreshold"


class VoltageAfterStim(EFeature):
    efel_name: ClassVar[str] = "voltage_after_stim"
    category: ClassVar[str] = "Subthreshold"


class DepolBlockBool(EFeature):
    efel_name: ClassVar[str] = "depol_block_bool"
    category: ClassVar[str] = "Subthreshold"


class OhmicInputResistanceVbSsse(EFeature):
    efel_name: ClassVar[str] = "ohmic_input_resistance_vb_ssse"
    category: ClassVar[str] = "Subthreshold"


class SagAmplitude(EFeature):
    efel_name: ClassVar[str] = "sag_amplitude"
    category: ClassVar[str] = "Subthreshold"


class SagRatio1(EFeature):
    efel_name: ClassVar[str] = "sag_ratio1"
    category: ClassVar[str] = "Subthreshold"


class SagRatio2(EFeature):
    efel_name: ClassVar[str] = "sag_ratio2"
    category: ClassVar[str] = "Subthreshold"


class DecayTimeConstantAfterStim(EFeature):
    efel_name: ClassVar[str] = "decay_time_constant_after_stim"
    category: ClassVar[str] = "Subthreshold"
