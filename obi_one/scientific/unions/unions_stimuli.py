from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    FullySynchronousSpikeStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    PoissonSpikeStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SinusoidalPoissonSpikeStimulus,
    SubthresholdCurrentClampSomaticStimulus,
)
from obi_one.scientific.blocks.stimuli.ornstein_uhlenbeck import (
    OrnsteinUhlenbeckCurrentSomaticStimulus,
    OrnsteinUhlenbeckConductanceSomaticStimulus,
    RelativeOrnsteinUhlenbeckCurrentSomaticStimulus,
    RelativeOrnsteinUhlenbeckConductanceSomaticStimulus
)

_INJECTION_STIMULI = (
    ConstantCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | RelativeNormallyDistributedCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus
    | OrnsteinUhlenbeckCurrentSomaticStimulus
    | OrnsteinUhlenbeckConductanceSomaticStimulus
    | RelativeOrnsteinUhlenbeckCurrentSomaticStimulus
    | RelativeOrnsteinUhlenbeckConductanceSomaticStimulus
)

_SPIKE_STIMULI = (
    PoissonSpikeStimulus
    | FullySynchronousSpikeStimulus
    | SinusoidalPoissonSpikeStimulus
)

StimulusUnion = Annotated[
    _INJECTION_STIMULI | _SPIKE_STIMULI,
    Discriminator("type"),
]

MEModelStimulusUnion = Annotated[
    _INJECTION_STIMULI,
    Discriminator("type"),
]


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
