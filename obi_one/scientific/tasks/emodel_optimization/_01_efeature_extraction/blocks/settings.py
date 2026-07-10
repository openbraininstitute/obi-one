"""Global extraction-flow settings for the e-feature extraction stage.

This block exposes the extraction-wide knobs that BluePyEModel's
``extract_save_features_protocols`` forwards to ``bluepyefe.extract``:

* the bluepyefe / ``EModelPipelineSettings`` extraction-flow knobs;
* the global-by-nature amplitude mode (``threshold_based``) and R_in / RMP
  protocol selectors.

Per-feature eFEL detection knobs (threshold, strict_stiminterval, interp_step,
stim_start, stim_end) and per-protocol/per-feature custom eFEL settings live on
:class:`EFeature` and :class:`Protocol` respectively. Global eFEL defaults are
defined as the module constant ``DEFAULT_EFEL_SETTINGS`` in ``task.py``.
"""

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class Settings(Block):
    """Global extraction-flow settings for the e-feature extraction stage."""

    # ------------------------------------------------------------------
    # bluepyefe / BluePyEModel extraction-flow settings
    # ------------------------------------------------------------------
    plot_extraction: bool = Field(
        default=True,
        title="Plot extraction",
        description="Whether to render extraction figures alongside the JSON output.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    compute_rheobase: bool = Field(
        default=True,
        title="Compute rheobase",
        description=(
            "When enabled, bluepyefe estimates each cell's rheobase from the"
            ' "IDthresh" protocol recordings using the default "absolute"'
            " strategy (lowest amplitude inducing at least 1 spike)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    default_std_value: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Default std value",
        description="Replaces zero standard deviations during feature extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    threshold_nvalue_save: int | list[int] = Field(
        default=1,
        title="Min values to save feature",
        description=(
            "bluepyefe ``threshold_nvalue_save``: minimum number of recordings a feature"
            " must be measured on to be kept in the output."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    pickle_cells: bool = Field(
        default=False,
        title="Pickle cells",
        description=(
            "bluepyefe ``pickle_cells``: also dump the BluePyEfe ``Cell`` objects as pickles."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    bound_max_std: bool = Field(
        default=False,
        title="Bound max std",
        description=(
            "If set, cap each feature's standard deviation at its mean value after extraction."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interpolate_rmp: bool = Field(
        default=False,
        title="Interpolate RMP",
        description=(
            "If set, estimate the resting membrane potential as ``V_hold - R_in * I_hold``"
            " when no zero-holding recording is available."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    threshold_efeature_std: float | None = Field(
        default=None,
        title="Threshold efeature std",
        description=(
            "If set, floor each feature's standard deviation at"
            " ``abs(threshold_efeature_std * mean)``. Leave empty to disable."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    minimum_protocol_delay: float | list[float] = Field(
        default=0.0,
        title="Minimum protocol delay",
        description="Protocols with a shorter initial delay are padded to this value (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # ------------------------------------------------------------------
    # Global-by-nature fields (Decision F: global, not per-protocol)
    # ------------------------------------------------------------------
    threshold_based: bool = Field(
        default=False,
        title="Threshold-based amplitudes",
        description=(
            "When enabled, extraction uses relative amplitudes (% of rheobase)"
            " from per-protocol ``extraction_amplitudes``. When disabled (default),"
            " amplitudes are auto-discovered in absolute nA from the NWB."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    rin_protocol_name: str | None = Field(
        default=None,
        title="R_in protocol name",
        description=(
            "Protocol used to compute input resistance (e.g. ``IV``). Only used"
            " when threshold_based is enabled. Leave empty to skip."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    rin_protocol_amplitude: float | None = Field(
        default=None,
        title="R_in protocol amplitude",
        description=(
            "Amplitude for the R_in protocol (e.g. ``-20``). Only used when"
            " threshold_based is enabled and rin_protocol_name is set."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    rmp_protocol_name: str | None = Field(
        default=None,
        title="RMP protocol name",
        description=(
            "Protocol used to compute resting membrane potential (e.g. ``IV``)."
            " Only used when threshold_based is enabled. Leave empty to skip."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    rmp_protocol_amplitude: float | None = Field(
        default=None,
        title="RMP protocol amplitude",
        description=(
            "Amplitude for the RMP protocol (e.g. ``0``). Only used when"
            " threshold_based is enabled and rmp_protocol_name is set."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    # ------------------------------------------------------------------
    # Validation hold-out (carried forward to Workflow A via recipe)
    # ------------------------------------------------------------------
    validation_protocols: tuple[str, ...] = Field(
        default=(),
        title="Validation protocols",
        description=(
            "Protocol names held out from optimisation and used only for"
            " validation. These protocols will still be extracted but marked"
            " with validation=True in the features JSON so the optimiser"
            " excludes them. Example: ('sAHP_220',). Leave empty to use all"
            " protocols for optimisation."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
