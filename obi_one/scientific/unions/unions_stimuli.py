from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.simulation.stimulus import (
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

StimulusUnion = (
    ConstantCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | RelativeNormallyDistributedCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | PoissonSpikeStimulus
    | FullySynchronousSpikeStimulus
)


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
