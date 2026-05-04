"""Ion channel equations."""

from abc import ABC
from typing import Annotated, Any, ClassVar

from pydantic import ConfigDict, Discriminator

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey


class IonChannelEquation(Block, ABC):
    """Abstract class for Ion Channel Equations. Only children of this class should be used."""

    equation_key: ClassVar[str] = ""

    title: ClassVar[str] = "Abstract class for Ion Channel Equations"


class SigFitMInf(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_minf"
    title: ClassVar[str] = r"Sigmoid equation for m_{\infty}"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: r"\frac{1}{1 + e^{\frac{ -(v - v_{half})}{k}}}",
        }
    )


class SigFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_mtau"
    title: ClassVar[str] = r"Sigmoid equation combination for \tau_m"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: (
                r"\frac{1.}{1. + e^{\frac{v - v_{break}}{3.}}}  \cdot "
                r"\frac{A_1}{1. + e^{ \frac{v - v_1}{-k_1}} }+ "
                r"( 1 - \frac{1.}{ 1. + e^{ \frac{v - v_{break}}{3.} } } ) \cdot "
                r" \frac{A_2}{ 1. + e^{ \frac{v - v_2}{k_2} } } "
            ),
        }
    )


class ThermoFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "thermo_fit_mtau"
    title: ClassVar[str] = r"Double exponential denominator equation for \tau_m"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: (
                r"\frac{1.}{ e^{ \frac{ -(v - v_1) }{k_1} } + e^{ \frac{v - v_2}{k_2} } }"
            )
        }
    )


class ThermoFitMTauV2(IonChannelEquation):
    equation_key: ClassVar[str] = "thermo_fit_mtau_v2"
    title: ClassVar[str] = (
        r"Double exponential denominator equation with slope constraint for \tau_m"
    )

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: (
                r"\frac{1.}{ e^{ \frac{-(v - v_1)}{ k / \delta } }"
                r" + e^{ \frac{v - v_2}{k / (1 - \delta)} } }"
            ),
        }
    )


class BellFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "bell_fit_mtau"
    title: ClassVar[str] = r"Bell equation for \tau_m"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: r"\frac{A}{e^{ \frac{ (v - v_{half}) ^ 2 }{k} }}"
        }
    )


class SigFitHInf(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_hinf"
    title: ClassVar[str] = r"Sigmoid equation for h_{\infty}"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: r"( 1 - A ) + \frac{A}{ 1 + e^{ \frac{v - v_{half}}{k} } }"
        }
    )


class SigFitHTau(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_htau"
    title: ClassVar[str] = r"Sigmoid equation for \tau_h"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.LATEX_EQUATION: r"A_1 + \frac{A_2}{1 + e^{ \frac{v - v_{half}}{k} }}"
        }
    )



_MINF_BLOCKS = SigFitMInf
MInfUnion = Annotated[
    _MINF_BLOCKS | None, Discriminator("type")
]  # None: have to use a dummy fallback because pydantic forces me to have a 'real' Union here

_MTAU_BLOCKS = SigFitMTau | ThermoFitMTau | ThermoFitMTauV2 | BellFitMTau
MTauUnion = Annotated[
    _MTAU_BLOCKS, Discriminator("type")
]

_HINF_BLOCKS = SigFitHInf
HInfUnion = Annotated[_HINF_BLOCKS | None, Discriminator("type")]


_HTAU_BLOCKS = SigFitHTau
HTauUnion = Annotated[_HTAU_BLOCKS | None, Discriminator("type")]


class MInfReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = MInfUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_MINF_BLOCKS)
    }


class MTauReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = MTauUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_MTAU_BLOCKS)
    }


class HInfReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = HInfUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_HINF_BLOCKS)
    }


class HTauReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = HTauUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_HTAU_BLOCKS)
    }
