"""Ion channel equations."""

from abc import ABC
from typing import Annotated, ClassVar

from ion_channel_builder.create_model import model_equations_mapping
from pydantic import Discriminator

from obi_one.core.block import Block


class IonChannelEquation(Block, ABC):
    """Abstract class for Ion Channel Equations. Only children of this class should be used."""

    equation_key: str = ""

    title: ClassVar[str] = "Abstract class for Ion Channel Equations"

    @property
    def equation_latex(self) -> str:
        return model_equations_mapping[self.equation_key]["equation_latex"]


class SigFitMInf(IonChannelEquation):
    equation_key: str = "sig_fit_minf"

    title: ClassVar[str] = r"Sigmoid equation for m_{\infty}"


class SigFitMTau(IonChannelEquation):
    equation_key: str = "sig_fit_mtau"

    title: ClassVar[str] = r"Sigmoid equation combination for \tau_m"


class ThermoFitMTau(IonChannelEquation):
    equation_key: str = "thermo_fit_mtau"

    title: ClassVar[str] = r"Double exponential denominator equation for \tau_m"


class ThermoFitMTauV2(IonChannelEquation):
    equation_key: str = "thermo_fit_mtau_v2"

    title: ClassVar[str] = (
        r"Double exponential denominator equation with slope constraint for \tau_m"
    )


class BellFitMTau(IonChannelEquation):
    equation_key: str = "bell_fit_mtau"

    title: ClassVar[str] = r"Bell equation for \tau_m"


class SigFitHInf(IonChannelEquation):
    equation_key: str = "sig_fit_hinf"

    title: ClassVar[str] = r"Sigmoid equation for h_{\infty}"


class SigFitHTau(IonChannelEquation):
    equation_key: str = "sig_fit_htau"

    title: ClassVar[str] = r"Sigmoid equation for \tau_h"


MInfUnion = Annotated[SigFitMInf, Discriminator("type")]

MTauUnion = Annotated[
    SigFitMTau | ThermoFitMTau | ThermoFitMTauV2 | BellFitMTau, Discriminator("type")
]

HInfUnion = Annotated[SigFitHInf, Discriminator("type")]

HTauUnion = Annotated[SigFitHTau, Discriminator("type")]
