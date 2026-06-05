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


class EFELSettings(Block):
    """``efel_settings`` block of ``pipeline_settings``."""

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

    def to_dict(self) -> dict:
        return {
            "Threshold": self.threshold,
            "interp_step": self.interp_step,
            "strict_stiminterval": self.strict_stiminterval,
        }


class ExtractionSettings(Block):
    """Top-level parameters forwarded to ``bluepyefe.extract.extract_efeatures``."""

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


class ECodeMetadata(Block):
    """Per-protocol timing + LJP metadata (single ``ecodes_metadata`` entry)."""

    ljp: float | list[float] = Field(
        default=14.0,
        title="Liquid junction potential",
        description="LJP correction in mV applied to recordings of this protocol.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
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

    def to_dict(self) -> dict:
        d: dict[str, float] = {"ljp": self.ljp}
        for key in ("ton", "toff", "tmid", "tmid2"):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        return d


class ProtocolTarget(Block):
    """Targets entry for a single protocol (one row in ``targets.py:targets``)."""

    # Tuples (not lists) so the framework keeps the value stable instead of
    # treating it as a sweep dimension — see ``Block`` docstring.
    amplitudes: tuple[float, ...] = Field(
        default=(),
        title="Amplitudes",
        description="Amplitudes (in pA) to extract features at.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    efeatures: tuple[str, ...] = Field(
        default=(),
        title="E-features",
        description="eFEL feature names to extract for this protocol.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    tolerance: float = Field(
        default=20.0,
        title="Tolerance",
        description="Amplitude tolerance (pA) used by ``configure_targets``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )


class ExtractionTargets(Block):
    """Targets/protocols configuration that drives ``bluepyefe.extract``.

    Mirrors the ``targets.py`` from the L5PC example — ecodes_metadata, targets,
    and protocols_rheobase. Defaults match the L5PC example.
    """

    ecodes_metadata: dict[str, ECodeMetadata] = Field(
        default_factory=lambda: {
            "IDthresh": ECodeMetadata(),
            "IDrest": ECodeMetadata(),
            "IV": ECodeMetadata(),
            "APWaveform": ECodeMetadata(),
            "sAHP": ECodeMetadata(),
        },
        title="Ecodes metadata",
        description=(
            "Per-protocol timing and LJP metadata. ``ton``/``toff`` default to"
            " ``None`` so bluepyefe auto-detects them from the current trace; set"
            " explicit values when the auto-detection picks up noise/artifacts."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY},
    )

    protocols_rheobase: tuple[str, ...] = Field(
        default=("IDthresh",),
        title="Rheobase protocols",
        description="Protocols used to determine the rheobase.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    targets: dict[str, ProtocolTarget] = Field(
        default_factory=lambda: {
            "IDrest": ProtocolTarget(
                amplitudes=(150, 250),
                efeatures=(
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
            "IV": ProtocolTarget(
                amplitudes=(0, -20, -100),
                efeatures=("voltage_base", "ohmic_input_resistance_vb_ssse"),
            ),
            "APWaveform": ProtocolTarget(
                amplitudes=(280,),
                efeatures=(
                    "AP_amplitude",
                    "AP1_amp",
                    "AP_duration_half_width",
                    "AHP_depth",
                ),
            ),
            "sAHP": ProtocolTarget(
                amplitudes=(220,),
                efeatures=("mean_frequency", "voltage_base", "depol_block_bool"),
            ),
        },
        title="Targets",
        description="Per-protocol amplitudes + efeatures to extract.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY},
    )
