"""Ion channel equations."""

from abc import ABC
from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference


class IonChannelEquation(Block, ABC):
    """Abstract class for Ion Channel Equations. Only children of this class should be used."""

    equation_key: ClassVar[str] = ""

    title: ClassVar[str] = "Abstract class for Ion Channel Equations"


class SigFitMInf(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_minf"
    title: ClassVar[str] = r"Sigmoid equation for m_{\infty}"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": r"\frac{1}{1 + e^{\frac{ -(v - v_{half})}{k}}}",
        }


class SigFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_mtau"
    title: ClassVar[str] = r"Sigmoid equation combination for \tau_m"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": (
                r"\frac{1.}{1. + e^{\frac{v - v_{break}}{3.}}}  \cdot "
                r"\frac{A_1}{1. + e^{ \frac{v - v_1}{-k_1}} }+ "
                r"( 1 - \frac{1.}{ 1. + e^{ \frac{v - v_{break}}{3.} } } ) \cdot "
                r" \frac{A_2}{ 1. + e^{ \frac{v - v_2}{k_2} } } "
            ),
        }


class ThermoFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "thermo_fit_mtau"
    title: ClassVar[str] = r"Double exponential denominator equation for \tau_m"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": (
                r"\frac{1.}{ e^{ \frac{ -(v - v_1) }{k_1} } + e^{ \frac{v - v_2}{k_2} } }"
            )
        }


class ThermoFitMTauV2(IonChannelEquation):
    equation_key: ClassVar[str] = "thermo_fit_mtau_v2"
    title: ClassVar[str] = (
        r"Double exponential denominator equation with slope constraint for \tau_m"
    )

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": (
                r"\frac{1.}{ e^{ \frac{-(v - v_1)}{ k / \delta } }"
                r" + e^{ \frac{v - v_2}{k / (1 - \delta)} } }"
            ),
        }


class BellFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "bellfit_mtau"
    title: ClassVar[str] = r"Bell equation for \tau_m"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": r"\frac{1.}{e^{ \frac{ (v - v_{half}) ^ 2 }{k} }}"
        }


class SigFitHInf(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_hinf"
    title: ClassVar[str] = r"Sigmoid equation for h_{\infty}"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": r"( 1 - A ) + \frac{A}{ 1 + e^{ \frac{v - v_{half}}{k} } }"
        }


class SigFitHTau(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_htau"
    title: ClassVar[str] = r"Sigmoid equation for \tau_h"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "latex_equation": r"A_1 + \frac{A_2}{1 + e^{ \frac{v - v_{half}}{k} }}"
        }


MInfUnion = Annotated[
    SigFitMInf | None, Discriminator("type")
]  # None: have to use a dummy fallback because pydantic forces me to have a 'real' Union here


MTauUnion = Annotated[
    SigFitMTau | ThermoFitMTau | ThermoFitMTauV2 | BellFitMTau, Discriminator("type")
]


HInfUnion = Annotated[SigFitHInf | None, Discriminator("type")]


HTauUnion = Annotated[SigFitHTau | None, Discriminator("type")]


class MInfReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = MInfUnion


class MTauReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = MTauUnion


class HInfReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = HInfUnion


class HTauReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = HTauUnion
