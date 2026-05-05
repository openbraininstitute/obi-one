"""Blocks for the 00_efeature_extraction stage.

Each block exposes a subset of the BluePyEModel ``pipeline_settings`` keys
that influence experimental e-feature extraction (see
https://github.com/openbraininstitute/BluePyEModel/blob/main/examples/L5PC/config/recipes.json).
The defaults match the L5PC example.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class ExtractionInitialize(Block):
    """Filesystem inputs for the extraction stage.

    All paths can be absolute or relative to the notebook's cwd; the task
    resolves them and copies the contents into the coord output's working
    directory before invoking BluePyEModel.
    """

    ephys_data_path: Path = Field(
        title="Ephys data path",
        description=(
            "Directory containing the experimental traces (`.ibw` for `file_type='ibw'`,"
            " `.nwb` for `file_type='nwb'`). The L5PC example downloads this via"
            " ``download_ephys_data.sh`` to ``./ephys_data/C060109A1-SR-C1/``."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    morphology_path: Path = Field(
        title="Morphologies path",
        description=(
            "Directory containing the morphology asc/swc/h5 files referenced from the"
            " recipe. Copied into the working directory at ``./morphologies/`` so it can"
            " be reused by the optimisation stage."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    mechanisms_path: Path = Field(
        title="Mechanisms path",
        description=(
            "Directory containing the NEURON ``.mod`` files. Copied to ``./mechanisms/``"
            " and compiled via ``nrnivmodl`` so the optimisation stage can run."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    params_path: Path = Field(
        title="Parameters JSON path",
        description=(
            "Path to the BluePyEModel parameters file (e.g. ``config/params/pyr.json``)."
            " Copied to ``./config/params/<basename>``; the path inside ``recipes.json``"
            " is preserved."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    recipes_path: Path = Field(
        title="Recipes JSON path",
        description=(
            "Path to a BluePyEModel ``recipes.json`` file. Copied to"
            " ``./config/recipes.json`` after the extraction-related"
            " ``pipeline_settings`` overrides have been merged in."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` to operate on (e.g. ``L5PC``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    species: str = Field(
        default="rat",
        title="Species",
        description="Species tag passed to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    brain_region: str = Field(
        default="SSCX",
        title="Brain region",
        description="Brain region tag passed to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    etype: str | None = Field(
        default=None,
        title="E-type",
        description="Optional electrical type tag.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    mtype: str | None = Field(
        default=None,
        title="M-type",
        description="Optional morphological type tag.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    ttype: str | None = Field(
        default=None,
        title="T-type",
        description="Optional transcriptomic type tag.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    use_multiprocessing: bool = Field(
        default=False,
        title="Use multiprocessing",
        description="Pass ``use_multiprocessing=True`` to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    use_ipyparallel: bool = Field(
        default=False,
        title="Use ipyparallel",
        description="Pass ``use_ipyparallel=True`` to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
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
    """Top-level ``pipeline_settings`` keys that drive feature extraction."""

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
        default="IV_-20",
        title="Rin protocol name",
        description="Protocol used to compute input resistance.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rmp_protocol: str | None = Field(
        default="IV_0",
        title="RMP protocol name",
        description="Protocol used to compute resting membrane potential.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    path_extract_config: str = Field(
        default="config/extract_config/L5PC_config.json",
        title="Extract config path",
        description=(
            "Relative path (under the working directory) where ``configure_targets``"
            " writes the auto-generated extraction config."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    def to_dict(self, efel: EFELSettings) -> dict[str, Any]:
        return {
            "plot_extraction": self.plot_extraction,
            "default_std_value": self.default_std_value,
            "extract_absolute_amplitudes": self.extract_absolute_amplitudes,
            "name_Rin_protocol": self.name_rin_protocol,
            "name_rmp_protocol": self.name_rmp_protocol,
            "path_extract_config": self.path_extract_config,
            "efel_settings": efel.to_dict(),
        }


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
    """Targets/protocols configuration that drives ``configure_targets()``.

    Mirrors the ``targets.py`` from the L5PC example — file_type, ecodes_metadata,
    targets, and protocols_rheobase. Defaults match the L5PC example so the
    bundled notebook works out of the box on the SSCx C060109A1-SR-C1 dataset.
    """

    file_type: Literal["ibw", "nwb"] = Field(
        default="ibw",
        title="File type",
        description="Format of the experimental traces (`ibw` or `nwb`).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    ecodes_metadata: dict[str, ECodeMetadata] = Field(
        default_factory=lambda: {
            "IDthresh": ECodeMetadata(ljp=14.0, ton=700, toff=2700),
            "IDrest": ECodeMetadata(ljp=14.0, ton=700, toff=2700),
            "IV": ECodeMetadata(ljp=14.0, ton=20, toff=1020),
            "APWaveform": ECodeMetadata(ljp=14.0, ton=5, toff=55),
            "sAHP": ECodeMetadata(ljp=14.0, ton=25, tmid=520, tmid2=720, toff=2720),
        },
        title="Ecodes metadata",
        description="Per-protocol timing and LJP metadata.",
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

    ibw_voltage_channel_pattern: str = Field(
        default="ch0",
        title="IBW voltage channel substring",
        description=(
            "Substring matching the voltage-channel filename in IBW datasets"
            " (BluePyEModel pairs `chN` voltage with `chN+1` current)."
        ),
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    ibw_current_channel_pattern: str = Field(
        default="ch1",
        title="IBW current channel substring",
        description="Substring used to derive the matching current trace from the voltage path.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    ibw_voltage_unit: str = Field(default="V", json_schema_extra={SchemaKey.UI_HIDDEN: True})
    ibw_current_unit: str = Field(default="A", json_schema_extra={SchemaKey.UI_HIDDEN: True})
    ibw_time_unit: str = Field(default="s", json_schema_extra={SchemaKey.UI_HIDDEN: True})
