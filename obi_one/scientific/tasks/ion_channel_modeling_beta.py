"""Ion channel modeling scan config, in the shape the scan-config UI can render.

Same fitting as `ion_channel_modeling`, reached through the generic scan-config editor
instead of the bespoke ion-channel build page. The science is not duplicated: the campaign
registration is the mixins from that module and the fitting is `IonChannelFittingTask`,
which this task subclasses to redirect only where the equations and gate exponents live.

The difference is how the four gating equations are offered. `IonChannelFittingScanConfig`
makes each one a referenced block; here they are keys on a single Hodgkin-Huxley model
block, which the UI draws as `block_single` holding four dropdowns.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import Field, StringConstraints

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.ion_channel_equations.ion_channel_equations import (
    EquationKey,
    equation_schema_extra,
)
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID
from obi_one.scientific.tasks.ion_channel_modeling import (
    IonChannelFittingTask,
    IonChannelModelingCampaignMixin,
    IonChannelModelingConfigMixin,
)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    MODEL = "Model"


class HodgkinHuxleyIonChannelModel(Block):
    """The channel model to fit: one equation per gating variable, plus their exponents."""

    title: ClassVar[str] = "Hodgkin-Huxley type ion channel model"

    minf_eq: Literal[EquationKey.SIG_FIT_MINF] = Field(
        title="m∞ equation",
        description=(
            r"Steady state activation parameter \( m_{\infty} \) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dm}{dt} = \frac{m_{\infty} - m}{\tau_{m}} \)"
        ),
        default=EquationKey.SIG_FIT_MINF,
        json_schema_extra=equation_schema_extra(EquationKey.SIG_FIT_MINF),
    )

    mtau_eq: Literal[
        EquationKey.SIG_FIT_MTAU,
        EquationKey.THERMO_FIT_MTAU,
        EquationKey.THERMO_FIT_MTAU_V2,
        EquationKey.BELL_FIT_MTAU,
    ] = Field(
        title="m time constant equation",
        description=(
            r"Activation time constant \(\tau_m\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dm}{dt} = \frac{m_{\infty} - m}{\tau_{m}} \)"
        ),
        default=EquationKey.SIG_FIT_MTAU,
        json_schema_extra=equation_schema_extra(
            EquationKey.SIG_FIT_MTAU,
            EquationKey.THERMO_FIT_MTAU,
            EquationKey.THERMO_FIT_MTAU_V2,
            EquationKey.BELL_FIT_MTAU,
        ),
    )

    hinf_eq: Literal[EquationKey.SIG_FIT_HINF] = Field(
        title="h∞ equation",
        description=(
            r"Steady state inactivation parameter \(h_{\infty}\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}} \)"
        ),
        default=EquationKey.SIG_FIT_HINF,
        json_schema_extra=equation_schema_extra(EquationKey.SIG_FIT_HINF),
    )

    htau_eq: Literal[EquationKey.SIG_FIT_HTAU] = Field(
        title="h time constant equation",
        description=(
            r"Inactivation time constant \(\tau_h\) equation. "
            r"This equation will be used for solving the differential equation: "
            r"\( \frac{dh}{dt} = \frac{h_{\infty} - h}{\tau_{h}} \)"
        ),
        default=EquationKey.SIG_FIT_HTAU,
        json_schema_extra=equation_schema_extra(EquationKey.SIG_FIT_HTAU),
    )

    m_power: int | list[int] = Field(
        title="m exponent in channel equation",
        default=1,
        ge=1,
        le=4,
        description=(
            r"Exponent \(p\) of \(m\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    h_power: int | list[int] = Field(
        title="h exponent in channel equation",
        default=1,
        ge=0,
        le=4,
        description=(
            r"Exponent \(q\) of \(h\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )


class IonChannelFittingBetaScanConfig(IonChannelModelingCampaignMixin, ScanConfig):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    name: ClassVar[str] = "Ion channel build (beta)"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.MODEL,
        ],
    }

    class Initialize(Block):
        recordings: IonChannelRecordingFromID | list[IonChannelRecordingFromID] = Field(
            title="Ion channel recording",
            description=(
                "Ion channel recordings to fit. Each recording is fitted on its own, so "
                "selecting several produces one ion channel model per recording."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE},
        )

        ion_channel_name: Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")] = (
            Field(
                title="Ion channel name",
                description=(
                    "The name you want to give to the generated ion channel model "
                    "(used as SUFFIX in the mod file). "
                    "Name must start with a letter or underscore, and can only contain "
                    "letters, numbers, and underscores."
                ),
                min_length=1,
                default="DefaultIonChannelName",
                json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
            )
        )

    info: Info = Field(
        title="Info",
        description="Information about the ion channel modeling campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the fitting.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    model_type: HodgkinHuxleyIonChannelModel = Field(
        title="Model",
        description=(
            "The Hodgkin-Huxley channel model to fit: an equation per gating variable, and "
            "the exponents p and q of m and h in the channel equation g = gbar * m^p * h^q."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.MODEL,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class IonChannelFittingBetaSingleConfig(
    IonChannelModelingConfigMixin, IonChannelFittingBetaScanConfig, SingleConfigMixin
):
    """Only allows single values and ensures nested attributes follow the same rule."""


class IonChannelFittingBetaTask(IonChannelFittingTask):
    """The fitting of `IonChannelFittingTask`, reading the model block for its choices."""

    config: IonChannelFittingBetaSingleConfig

    @property
    def equation_keys(self) -> dict[str, str]:
        return {
            "minf": self.config.model_type.minf_eq,
            "mtau": self.config.model_type.mtau_eq,
            "hinf": self.config.model_type.hinf_eq,
            "htau": self.config.model_type.htau_eq,
        }

    @property
    def m_power(self) -> int:
        return self.config.model_type.m_power  # ty:ignore[invalid-return-type]

    @property
    def h_power(self) -> int:
        return self.config.model_type.h_power  # ty:ignore[invalid-return-type]
