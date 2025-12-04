from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimulus import (
    ConstantCurrentClampStimulus,
    FullySynchronousSpikeStimulus,
    HyperpolarizingCurrentClampStimulus,
    LinearCurrentClampStimulus,
    MultiPulseCurrentClampStimulus,
    NormallyDistributedCurrentClampStimulus,
    PoissonSpikeStimulus,
    RelativeConstantCurrentClampStimulus,
    RelativeLinearCurrentClampStimulus,
    RelativeNormallyDistributedCurrentClampStimulus,
    SinusoidalCurrentClampStimulus,
    SinusoidalPoissonSpikeStimulus,
    SubthresholdCurrentClampStimulus,
)

StimulusUnion = Annotated[
    ConstantCurrentClampStimulus
    | HyperpolarizingCurrentClampStimulus
    | LinearCurrentClampStimulus
    | MultiPulseCurrentClampStimulus
    | NormallyDistributedCurrentClampStimulus
    | RelativeNormallyDistributedCurrentClampStimulus
    | RelativeConstantCurrentClampStimulus
    | RelativeLinearCurrentClampStimulus
    | SinusoidalCurrentClampStimulus
    | SubthresholdCurrentClampStimulus
    | PoissonSpikeStimulus
    | FullySynchronousSpikeStimulus
    | SinusoidalPoissonSpikeStimulus,
    Discriminator("type"),
]

MEModelStimulusUnion = Annotated[
    ConstantCurrentClampStimulus
    | HyperpolarizingCurrentClampStimulus
    | LinearCurrentClampStimulus
    | MultiPulseCurrentClampStimulus
    | NormallyDistributedCurrentClampStimulus
    | RelativeNormallyDistributedCurrentClampStimulus
    | RelativeConstantCurrentClampStimulus
    | RelativeLinearCurrentClampStimulus
    | SinusoidalCurrentClampStimulus
    | SubthresholdCurrentClampStimulus,
    Discriminator("type"),
]


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
