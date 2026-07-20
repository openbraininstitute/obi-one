"""Base eFEL feature model, holding the knobs shared by every feature.

:class:`EFeature` carries what the user can tune for one feature: whether to
extract it, its weight and tolerance, and per-feature eFEL detection settings.

It is never used directly. The concrete classes in :mod:`.efeature_types` fix
``efel_name``, and their category intermediate fixes ``category`` — which is
what groups them for the UI's "Add feature" modal. Categories follow the eFEL
documentation (https://efel.readthedocs.io/en/latest/eFeatures.html): Spike
event, Spike shape, Subthreshold.
"""

from typing import ClassVar

from pydantic import Field, PositiveFloat

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class EFeature(OBIBaseModel):
    """Generic eFEL feature with per-feature tunable parameters.

    Each instance carries:
    - ``efel_name``: the eFEL feature key (e.g. ``"mean_frequency"``)
    - ``category``: UI grouping (one of the 4 eFEL doc categories)
    - ``extract``: on/off switch for inclusion in extraction
    - ``weight``, ``tolerance``: fitness function parameters
    - Per-feature eFEL setting overrides (threshold, stim window, custom)

    The three always-present eFEL settings (``Threshold``,
    ``strict_stiminterval``, ``interp_step``) default to eFEL's own defaults
    and are always emitted in ``efel_settings_override()``. Two additional
    optional fields (``stim_start``, ``stim_end``) are emitted only when set.
    Further eFEL settings can be added via ``custom_efel_settings``.
    """

    efel_name: str = Field(
        default="",
        title="eFEL feature name",
        description="The eFEL feature key (e.g. 'mean_frequency', 'AP_amplitude').",
    )
    category: str = Field(
        default="Spike event",
        title="Category",
        description=(
            "Feature category for UI grouping. One of: 'Spike event',"
            " 'Spike shape', 'Subthreshold'."
        ),
    )

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
    efeature_name: str = Field(
        default="",
        title="Feature name",
        description=(
            "Custom name for this target (bluepyefe ``efeature_name``). Lets the"
            " same eFEL feature be extracted under a distinct label, e.g."
            " ``Spikecount_phase1``. Leave empty to use the eFEL feature name."
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
            "eFEL ``interp_step``: time step the trace is resampled to before extraction (ms)."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # ------------------------------------------------------------------
    # Optional per-feature stimulus window overrides
    # ------------------------------------------------------------------
    stim_start: float = Field(
        default=0.0,
        title="Stim start",
        description=(
            "eFEL ``stim_start``: stimulus onset time for this feature (ms)."
            " Overrides the protocol-level value. Set to 0 to use the"
            " protocol's detected onset."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    stim_end: float = Field(
        default=0.0,
        title="Stim end",
        description=(
            "eFEL ``stim_end``: stimulus end time for this feature (ms)."
            " Overrides the protocol-level value. Set to 0 to use the"
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
    custom_efel_settings: dict[str, float | bool] = Field(
        default_factory=dict,
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
        ``stim_end`` are emitted only when non-zero. Additional settings from
        ``custom_efel_settings`` are merged on top. Each setting overrides the
        protocol- and global-level eFEL setting for this feature.
        """
        overrides: dict[str, float | bool] = {
            "Threshold": self.threshold,
            "strict_stiminterval": self.strict_stiminterval,
            "interp_step": self.interp_step,
        }
        if self.stim_start:
            overrides["stim_start"] = self.stim_start
        if self.stim_end:
            overrides["stim_end"] = self.stim_end
        if self.custom_efel_settings:
            overrides.update(self.custom_efel_settings)
        return overrides
