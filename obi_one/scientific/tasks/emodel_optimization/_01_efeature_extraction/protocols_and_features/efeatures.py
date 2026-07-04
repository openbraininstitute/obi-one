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
    target rows). Fields mirror the per-target tunable parameters of
    ``bluepyefe.target.EFeatureTarget``: ``tolerance`` and ``efel_settings``
    overrides. ``weight`` is forwarded downstream to the fitness-calculator
    configuration. ``extract`` is the on/off switch consumed by
    ``Protocol.selected_efeatures``.

    The three always-present eFEL settings (``Threshold``,
    ``strict_stiminterval``, ``interp_step``) default to eFEL's own defaults
    and are always emitted in ``efel_settings_override()``. Additional eFEL
    settings can be added via ``custom_efel_settings``.
    """

    efel_name: ClassVar[str]
    efel_doc_url: ClassVar[str] = "https://efel.readthedocs.io/en/latest/eFeatures.html"

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

    # Always-present eFEL settings with eFEL defaults pre-filled. These are
    # always emitted in ``efel_settings_override()`` and override the protocol-
    # and global-level values (global -> protocol -> feature).
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
    # Additional eFEL settings beyond the 3 always-present ones. Keys are eFEL
    # setting names (e.g. ``"DerivativeThreshold"``, ``"stim_start"``); values
    # are ``float`` or ``bool``. ``None`` means no custom settings.
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

        The 3 always-present settings are always emitted. Additional settings
        from ``custom_efel_settings`` are merged on top. Each setting overrides
        the protocol- and global-level eFEL setting for this feature.
        """
        overrides: dict[str, float | bool] = {
            "Threshold": self.threshold,
            "strict_stiminterval": self.strict_stiminterval,
            "interp_step": self.interp_step,
        }
        if self.custom_efel_settings:
            overrides.update(self.custom_efel_settings)
        return overrides


class Spikecount(EFeature):
    efel_name: ClassVar[str] = "Spikecount"


class DepolBlockBool(EFeature):
    efel_name: ClassVar[str] = "depol_block_bool"


class VoltageBase(EFeature):
    efel_name: ClassVar[str] = "voltage_base"


class VoltageAfterStim(EFeature):
    efel_name: ClassVar[str] = "voltage_after_stim"


class MeanFrequency(EFeature):
    efel_name: ClassVar[str] = "mean_frequency"


class TimeToFirstSpike(EFeature):
    efel_name: ClassVar[str] = "time_to_first_spike"


class TimeToLastSpike(EFeature):
    efel_name: ClassVar[str] = "time_to_last_spike"


class InvTimeToFirstSpike(EFeature):
    efel_name: ClassVar[str] = "inv_time_to_first_spike"


class InvFirstISI(EFeature):
    efel_name: ClassVar[str] = "inv_first_ISI"


class InvSecondISI(EFeature):
    efel_name: ClassVar[str] = "inv_second_ISI"


class InvThirdISI(EFeature):
    efel_name: ClassVar[str] = "inv_third_ISI"


class InvLastISI(EFeature):
    efel_name: ClassVar[str] = "inv_last_ISI"


class ISICV(EFeature):
    efel_name: ClassVar[str] = "ISI_CV"


class ISILogSlope(EFeature):
    efel_name: ClassVar[str] = "ISI_log_slope"


class DoubletISI(EFeature):
    efel_name: ClassVar[str] = "doublet_ISI"


class AHPDepth(EFeature):
    efel_name: ClassVar[str] = "AHP_depth"


class AHPTimeFromPeak(EFeature):
    efel_name: ClassVar[str] = "AHP_time_from_peak"


class MinAHPValues(EFeature):
    efel_name: ClassVar[str] = "min_AHP_values"


class StrictBurstNumber(EFeature):
    efel_name: ClassVar[str] = "strict_burst_number"


class StrictBurstMeanFreq(EFeature):
    efel_name: ClassVar[str] = "strict_burst_mean_freq"


class NumberInitialSpikes(EFeature):
    efel_name: ClassVar[str] = "number_initial_spikes"


class IrregularityIndex(EFeature):
    efel_name: ClassVar[str] = "irregularity_index"


class AdaptationIndex(EFeature):
    efel_name: ClassVar[str] = "adaptation_index"


class OhmicInputResistanceVbSsse(EFeature):
    efel_name: ClassVar[str] = "ohmic_input_resistance_vb_ssse"


class SagAmplitude(EFeature):
    efel_name: ClassVar[str] = "sag_amplitude"


class SagRatio1(EFeature):
    efel_name: ClassVar[str] = "sag_ratio1"


class SagRatio2(EFeature):
    efel_name: ClassVar[str] = "sag_ratio2"


class DecayTimeConstantAfterStim(EFeature):
    efel_name: ClassVar[str] = "decay_time_constant_after_stim"


class APAmplitude(EFeature):
    efel_name: ClassVar[str] = "AP_amplitude"


class AP1Amp(EFeature):
    efel_name: ClassVar[str] = "AP1_amp"


class APDurationHalfWidth(EFeature):
    efel_name: ClassVar[str] = "AP_duration_half_width"


class APBeginVoltage(EFeature):
    efel_name: ClassVar[str] = "AP_begin_voltage"


class APBeginWidth(EFeature):
    efel_name: ClassVar[str] = "AP_begin_width"
