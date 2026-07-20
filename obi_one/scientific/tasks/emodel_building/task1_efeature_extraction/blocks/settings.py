"""Global extraction-flow settings for the e-feature extraction stage.

Advanced extraction knobs that BluePyEModel's
``extract_save_features_protocols`` forwards to ``bluepyefe.extract``.

Per-protocol settings (Rin, RMP, rheobase, threshold_based, timing, LJP)
live on :class:`Protocol`. Per-feature eFEL detection knobs live on
:class:`EFeature`. This block contains only the statistical/output settings
that apply globally across all protocols.
"""

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class Settings(Block):
    """Advanced extraction settings (statistical knobs and output toggles)."""

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
    threshold_nvalue_save: int | list[int] = Field(
        default=1,
        title="Min values to save feature",
        description=(
            "bluepyefe ``threshold_nvalue_save``: minimum number of recordings a feature"
            " must be measured on to be kept in the output."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
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
    threshold_efeature_std: float | list[float] = Field(
        default=0.0,
        title="Threshold efeature std",
        description=(
            "Floor each feature's standard deviation at"
            " ``abs(threshold_efeature_std * mean)``. Set to 0 to disable."
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
    validation_protocols: str = Field(
        default="",
        title="Validation protocols",
        description=(
            "Comma-separated protocol names held out from optimisation and used"
            " only for validation. These protocols will still be extracted but"
            " marked with validation=True in the features JSON so the optimiser"
            " excludes them. Example: 'sAHP'. Leave empty to use all"
            " protocols for optimisation."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
