from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimulus import (
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
    SubthresholdCurrentClampSomaticStimulus,
)

StimulusUnion = Annotated[
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
    | PoissonSpikeStimulus
    | FullySynchronousSpikeStimulus,
    Discriminator("type"),
]

MEModelStimulusUnion = Annotated[
    ConstantCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | RelativeNormallyDistributedCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus,
    Discriminator("type"),
]


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
