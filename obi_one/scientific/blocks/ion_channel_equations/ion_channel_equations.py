"""Ion channel equations."""

from enum import StrEnum
from typing import Any

from obi_one.core.schema import SchemaKey, UIElement


class EquationKey(StrEnum):
    """Fitting keys understood by `ion_channel_builder`."""

    SIG_FIT_MINF = "sig_fit_minf"
    SIG_FIT_MTAU = "sig_fit_mtau"
    THERMO_FIT_MTAU = "thermo_fit_mtau"
    THERMO_FIT_MTAU_V2 = "thermo_fit_mtau_v2"
    BELL_FIT_MTAU = "bell_fit_mtau"
    SIG_FIT_HINF = "sig_fit_hinf"
    SIG_FIT_HTAU = "sig_fit_htau"


EQUATION_TITLES: dict[str, str] = {
    EquationKey.SIG_FIT_MINF: "Sigmoid equation for m∞",
    EquationKey.SIG_FIT_MTAU: "Sigmoid equation combination for τₘ",
    EquationKey.THERMO_FIT_MTAU: "Double exponential denominator equation for τₘ",
    EquationKey.THERMO_FIT_MTAU_V2: (
        "Double exponential denominator equation with slope constraint for τₘ"
    ),
    EquationKey.BELL_FIT_MTAU: "Bell equation for τₘ",
    EquationKey.SIG_FIT_HINF: "Sigmoid equation for h∞",
    EquationKey.SIG_FIT_HTAU: "Sigmoid equation for τₕ",
}

EQUATION_LATEX: dict[str, str] = {
    EquationKey.SIG_FIT_MINF: r"\frac{1}{1 + e^{\frac{ -(v - v_{half})}{k}}}",
    EquationKey.SIG_FIT_MTAU: (
        r"\frac{1.}{1. + e^{\frac{v - v_{break}}{3.}}}  \cdot "
        r"\frac{A_1}{1. + e^{ \frac{v - v_1}{-k_1}} }+ "
        r"( 1 - \frac{1.}{ 1. + e^{ \frac{v - v_{break}}{3.} } } ) \cdot "
        r" \frac{A_2}{ 1. + e^{ \frac{v - v_2}{k_2} } } "
    ),
    EquationKey.THERMO_FIT_MTAU: (
        r"\frac{1.}{ e^{ \frac{ -(v - v_1) }{k_1} } + e^{ \frac{v - v_2}{k_2} } }"
    ),
    EquationKey.THERMO_FIT_MTAU_V2: (
        r"\frac{1.}{ e^{ \frac{-(v - v_1)}{ k / \delta } }"
        r" + e^{ \frac{v - v_2}{k / (1 - \delta)} } }"
    ),
    EquationKey.BELL_FIT_MTAU: r"\frac{A}{e^{ \frac{ (v - v_{half}) ^ 2 }{k} }}",
    EquationKey.SIG_FIT_HINF: r"( 1 - A ) + \frac{A}{ 1 + e^{ \frac{v - v_{half}}{k} } }",
    EquationKey.SIG_FIT_HTAU: r"A_1 + \frac{A_2}{1 + e^{ \frac{v - v_{half}}{k} }}",
}


def equation_schema_extra(schema: dict[str, Any]) -> None:
    """Render a `Literal` equation field as a dropdown of its keys.

    A `Literal` of one key serialises to `const`, which the UI reads as a block's `type`
    discriminator and hides, while `string_selection_enhanced` renders from `enum`.
    """
    keys = schema.pop("enum", None) or [schema.pop("const")]
    schema["enum"] = keys
    schema[SchemaKey.UI_ELEMENT] = UIElement.STRING_SELECTION_ENHANCED
    schema[SchemaKey.TITLE_BY_KEY] = {key: EQUATION_TITLES[key] for key in keys}
    schema[SchemaKey.LATEX_BY_KEY] = {key: EQUATION_LATEX[key] for key in keys}
