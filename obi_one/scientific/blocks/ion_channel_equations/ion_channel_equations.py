"""Ion channel equations."""

from abc import ABC
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any, ClassVar

from pydantic import ConfigDict, Discriminator

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey, UIElement


class IonChannelEquation(Block, ABC):
    """Abstract class for Ion Channel Equations. Only children of this class should be used."""

    equation_key: ClassVar[str] = ""
    latex: ClassVar[str] = ""
    # `title` is LaTeX, which the bespoke ion-channel build page renders itself. The generic
    # scan-config editor renders a dropdown option's title as plain text, so it reads this.
    display_title: ClassVar[str] = ""

    title: ClassVar[str] = "Abstract class for Ion Channel Equations"


class SigFitMInf(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_minf"
    title: ClassVar[str] = r"Sigmoid equation for m_{\infty}"
    display_title: ClassVar[str] = "Sigmoid equation for m∞"
    latex: ClassVar[str] = r"\frac{1}{1 + e^{\frac{ -(v - v_{half})}{k}}}"

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


class SigFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_mtau"
    title: ClassVar[str] = r"Sigmoid equation combination for \tau_m"
    display_title: ClassVar[str] = "Sigmoid equation combination for τm"
    latex: ClassVar[str] = (
        r"\frac{1.}{1. + e^{\frac{v - v_{break}}{3.}}}  \cdot "
        r"\frac{A_1}{1. + e^{ \frac{v - v_1}{-k_1}} }+ "
        r"( 1 - \frac{1.}{ 1. + e^{ \frac{v - v_{break}}{3.} } } ) \cdot "
        r" \frac{A_2}{ 1. + e^{ \frac{v - v_2}{k_2} } } "
    )

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


class ThermoFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "thermo_fit_mtau"
    title: ClassVar[str] = r"Double exponential denominator equation for \tau_m"
    display_title: ClassVar[str] = "Double exponential denominator equation for τm"
    latex: ClassVar[str] = (
        r"\frac{1.}{ e^{ \frac{ -(v - v_1) }{k_1} } + e^{ \frac{v - v_2}{k_2} } }"
    )

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


class ThermoFitMTauV2(IonChannelEquation):
    equation_key: ClassVar[str] = "thermo_fit_mtau_v2"
    title: ClassVar[str] = (
        r"Double exponential denominator equation with slope constraint for \tau_m"
    )
    display_title: ClassVar[str] = (
        "Double exponential denominator equation with slope constraint for τm"
    )
    latex: ClassVar[str] = (
        r"\frac{1.}{ e^{ \frac{-(v - v_1)}{ k / \delta } }"
        r" + e^{ \frac{v - v_2}{k / (1 - \delta)} } }"
    )

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


class BellFitMTau(IonChannelEquation):
    equation_key: ClassVar[str] = "bell_fit_mtau"
    title: ClassVar[str] = r"Bell equation for \tau_m"
    display_title: ClassVar[str] = "Bell equation for τm"
    latex: ClassVar[str] = r"\frac{A}{e^{ \frac{ (v - v_{half}) ^ 2 }{k} }}"

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


class SigFitHInf(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_hinf"
    title: ClassVar[str] = r"Sigmoid equation for h_{\infty}"
    display_title: ClassVar[str] = "Sigmoid equation for h∞"
    latex: ClassVar[str] = r"( 1 - A ) + \frac{A}{ 1 + e^{ \frac{v - v_{half}}{k} } }"

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


class SigFitHTau(IonChannelEquation):
    equation_key: ClassVar[str] = "sig_fit_htau"
    title: ClassVar[str] = r"Sigmoid equation for \tau_h"
    display_title: ClassVar[str] = "Sigmoid equation for τh"
    latex: ClassVar[str] = r"A_1 + \frac{A_2}{1 + e^{ \frac{v - v_{half}}{k} }}"

    model_config = ConfigDict(json_schema_extra={SchemaKey.LATEX_EQUATION: latex})


_MINF_BLOCKS = SigFitMInf
MInfUnion = Annotated[
    _MINF_BLOCKS | None, Discriminator("type")
]  # None: have to use a dummy fallback because pydantic forces me to have a 'real' Union here

_MTAU_BLOCKS = SigFitMTau | ThermoFitMTau | ThermoFitMTauV2 | BellFitMTau
MTauUnion = Annotated[_MTAU_BLOCKS, Discriminator("type")]

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


class EquationKey(StrEnum):
    """Fitting keys understood by `ion_channel_builder`.

    The same strings as the `equation_key` of each block above, in an enum so that a
    ScanConfig can offer them as a `Literal` dropdown instead of a block reference.
    """

    SIG_FIT_MINF = "sig_fit_minf"
    SIG_FIT_MTAU = "sig_fit_mtau"
    THERMO_FIT_MTAU = "thermo_fit_mtau"
    THERMO_FIT_MTAU_V2 = "thermo_fit_mtau_v2"
    BELL_FIT_MTAU = "bell_fit_mtau"
    SIG_FIT_HINF = "sig_fit_hinf"
    SIG_FIT_HTAU = "sig_fit_htau"


_EQUATION_BLOCK_BY_KEY: dict[str, type[IonChannelEquation]] = {
    block.equation_key: block
    for block in (
        SigFitMInf,
        SigFitMTau,
        ThermoFitMTau,
        ThermoFitMTauV2,
        BellFitMTau,
        SigFitHInf,
        SigFitHTau,
    )
}


def equation_schema_extra(*keys: EquationKey) -> Callable[[dict[str, Any]], None]:
    """Schema extras for a `Literal` equation field offering `keys`.

    The titles and formulas come from the equation blocks above, so the dropdown and the
    block definitions cannot drift apart.

    A callable rather than a dict so the generated schema can be edited and not only added
    to: a `Literal` of one key serialises to `const`, which the UI reads as a block's `type`
    discriminator and hides, while `string_selection_enhanced` renders from `enum` however
    many keys there are.
    """
    blocks = {key: _EQUATION_BLOCK_BY_KEY[key] for key in keys}

    def apply(schema: dict[str, Any]) -> None:
        schema.pop("const", None)
        schema["enum"] = [str(key) for key in keys]
        schema[SchemaKey.UI_ELEMENT] = UIElement.STRING_SELECTION_ENHANCED
        schema[SchemaKey.TITLE_BY_KEY] = {
            str(key): block.display_title for key, block in blocks.items()
        }
        schema[SchemaKey.LATEX_BY_KEY] = {str(key): block.latex for key, block in blocks.items()}

    return apply
