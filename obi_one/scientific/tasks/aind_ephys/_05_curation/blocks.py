"""Blocks for the curation stage of the AIND ephys pipeline.

Defaults are those of the AIND pipeline's ``default_params.json``.
"""

import copy

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement

# Bombcell thresholds by label, metric and bound, in spikeinterface's ``bombcell_label_units`` form.
DEFAULT_BOMBCELL_THRESHOLDS = {
    "noise": {
        "num_positive_peaks": {"greater": None, "less": 2},
        "num_negative_peaks": {"greater": None, "less": 1},
        "peak_to_trough_duration": {"greater": 0.0001, "less": 0.00115},
        "waveform_baseline_flatness": {"greater": None, "less": 0.5},
        "peak_after_to_trough_ratio": {"greater": None, "less": 0.8},
        "exp_decay": {"greater": 0.01, "less": 0.1},
    },
    "mua": {
        "amplitude_median": {"greater": 30, "less": None, "abs": True},
        "snr": {"greater": 5, "less": None},
        "amplitude_cutoff": {"greater": None, "less": 0.2},
        "num_spikes": {"greater": 300, "less": None},
        "rp_contamination": {"greater": None, "less": 0.1},
        "presence_ratio": {"greater": 0.7, "less": None},
        "drift_ptp": {"greater": None, "less": 100},
    },
    "non-somatic": {
        "peak_before_to_trough_ratio": {"greater": None, "less": 3},
        "peak_before_width": {"greater": 0.00015, "less": None},
        "trough_width": {"greater": 0.0002, "less": None},
        "peak_before_to_peak_after_ratio": {"greater": None, "less": 3},
        "main_peak_to_trough_ratio": {"greater": None, "less": 0.8},
    },
}


class QCThresholds(Block):
    """Thresholds of the default QC, which every unit passes or fails."""

    rp_contamination_max: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.5,
        title="Max refractory-period contamination",
        description="Units more contaminated fail.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    presence_ratio_min: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.8,
        title="Min presence ratio",
        description="Units present in a smaller fraction of the recording fail.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    amplitude_cutoff_max: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.1,
        title="Max amplitude cutoff",
        description="Units with more of their amplitude distribution cut off fail.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {
            "rp_contamination": {"less": self.rp_contamination_max},
            "presence_ratio": {"greater": self.presence_ratio_min},
            "amplitude_cutoff": {"less": self.amplitude_cutoff_max},
        }


class UnitRefine(Block):
    """UnitRefine classifiers, downloaded from Hugging Face; no classifiers skips UnitRefine."""

    noise_neural_classifier: str | None = Field(
        default="SpikeInterface/UnitRefine_noise_neural_classifier",
        title="Noise/neural classifier",
        description="Hugging Face repository of the classifier telling noise from neural units.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    sua_mua_classifier: str | None = Field(
        default="SpikeInterface/UnitRefine_sua_mua_classifier",
        title="SUA/MUA classifier",
        description="Hugging Face repository of the classifier telling single from multi units.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )


class Bombcell(Block):
    """Bombcell labelling of units as good, MUA, noise or non-somatic."""

    thresholds: dict = Field(
        default_factory=lambda: copy.deepcopy(DEFAULT_BOMBCELL_THRESHOLDS),
        title="Thresholds",
        description="Bounds on each metric, by label; a bound of None is not applied.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )


class Slay(Block):
    """SLAy search for pairs of units to merge."""

    templates_diff: PositiveFloat | list[PositiveFloat] = Field(
        default=0.35,
        title="Template difference",
        description="Largest template difference of a candidate pair.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    k1: PositiveFloat | list[PositiveFloat] = Field(
        default=0.25,
        title="k1",
        description="SLAy's weight of the template similarity.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    k2: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="k2",
        description="SLAy's weight of the cross-correlogram significance.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    slay_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=0.4,
        title="SLAy threshold",
        description="Score above which a pair is proposed for merging.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {
            "template_similarity": {"templates_diff": self.templates_diff},
            "slay": {"k1": self.k1, "k2": self.k2, "slay_threshold": self.slay_threshold},
        }
