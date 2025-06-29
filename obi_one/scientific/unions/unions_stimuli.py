from obi_one.scientific.simulation.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SubthresholdCurrentClampSomaticStimulus,
    PoissonSpikeStimulus,
    FullySynchronousSpikeStimulus
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

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""
    
    allowed_block_types: ClassVar[Any] = StimulusUnion