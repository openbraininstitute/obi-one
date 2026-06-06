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


class EFeature(OBIBaseModel):
    """Base class for tunable bluepyefe e-features.

    Subclasses declare ``efel_name`` (the eFEL feature key used in bluepyefe
    target rows). Fields mirror the per-target tunable parameters of
    ``bluepyefe.target.EFeatureTarget``: ``tolerance`` and ``efel_settings``
    overrides (``Threshold``, ``stim_start``, ``stim_end``). ``weight`` is
    forwarded downstream to the fitness-calculator configuration. ``extract``
    is the on/off switch consumed by ``Protocol.selected_efeatures``.
    """

    efel_name: ClassVar[str]

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
    threshold: float | None = Field(
        default=None,
        title="Threshold",
        description="Per-feature override of eFEL's ``Threshold`` (spike detection, mV).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    stim_start: float | None = Field(
        default=None,
        title="Stim start",
        description="Per-feature override of eFEL's ``stim_start`` (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    stim_end: float | None = Field(
        default=None,
        title="Stim end",
        description="Per-feature override of eFEL's ``stim_end`` (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def efel_settings_override(self) -> dict:
        """Build the ``efel_settings`` dict for this feature's bluepyefe target row."""
        d: dict[str, float] = {}
        if self.threshold is not None:
            d["Threshold"] = self.threshold
        if self.stim_start is not None:
            d["stim_start"] = self.stim_start
        if self.stim_end is not None:
            d["stim_end"] = self.stim_end
        return d


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
