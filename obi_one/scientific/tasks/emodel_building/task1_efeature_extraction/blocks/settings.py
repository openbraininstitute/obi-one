"""Global extraction-flow settings for the e-feature extraction stage.

Advanced extraction knobs that BluePyEModel's
``extract_save_features_protocols`` forwards to ``bluepyefe.extract``.

Per-protocol settings (Rin, RMP, rheobase, threshold_based, timing)
live on :class:`Protocol`. Per-feature eFEL detection knobs live on
:class:`EFeature`. This block contains only the statistical/output settings
that apply globally across all protocols.
"""

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.constants import (
    SPIKE_DETECTION_THRESHOLD_DESCRIPTION,
    SPIKE_DETECTION_THRESHOLD_TITLE,
    TRACE_RESAMPLING_TIMESTEP_DESCRIPTION,
    TRACE_RESAMPLING_TIMESTEP_TITLE,
)


class Settings(Block):
    """Advanced extraction settings (statistical knobs and output toggles).

    Also holds the global eFEL detection knobs (``spike_detection_threshold``,
    ``trace_resampling_timestep``) — the base of the settings cascade. Protocols
    and features may override them (feature > protocol > global); left unset
    there, the global value applies.
    """

    # -- Global eFEL detection knobs (base of the cascade) --------------------
    spike_detection_threshold: float | None = Field(
        default=-20.0,
        title=SPIKE_DETECTION_THRESHOLD_TITLE,
        description=SPIKE_DETECTION_THRESHOLD_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    trace_resampling_timestep: PositiveFloat | None = Field(
        default=0.025,
        title=TRACE_RESAMPLING_TIMESTEP_TITLE,
        description=TRACE_RESAMPLING_TIMESTEP_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
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

    def global_efel_settings(self) -> dict:
        """Return the global eFEL settings dict — the base of the cascade.

        ``strict_stiminterval`` is fixed to True (only count spikes strictly within
        the stimulus interval) rather than exposed as a setting. A threshold or
        resampling timestep left unset (None) is omitted so eFEL falls back to its
        own default.
        """
        efel_settings: dict[str, float | bool] = {"strict_stiminterval": True}
        if self.spike_detection_threshold is not None:
            efel_settings["Threshold"] = self.spike_detection_threshold
        if self.trace_resampling_timestep is not None:
            efel_settings["interp_step"] = self.trace_resampling_timestep
        return efel_settings
