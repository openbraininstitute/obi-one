"""Combined eFEL and ``bluepyefe.extract`` settings for the extraction stage."""

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class Settings(Block):
    """Combined eFEL and ``bluepyefe.extract`` settings for the extraction stage."""

    # ``efel_settings`` block of ``pipeline_settings``.
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

    # Top-level parameters forwarded to ``bluepyefe.extract.extract_efeatures``.
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
    protocols_rheobase: tuple[str, ...] = Field(
        default=("IDthresh",),
        title="Rheobase protocols",
        description="Protocols used to determine the rheobase.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
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

    def efel_to_dict(self) -> dict:
        return {
            "Threshold": self.threshold,
            "interp_step": self.interp_step,
            "strict_stiminterval": self.strict_stiminterval,
        }
