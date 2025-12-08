from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimulus import (
    # Deprecated somatic aliases (backward compatibility)
    ConstantCurrentClampSomaticStimulus,
    # New unified stimulus classes
    ConstantCurrentClampStimulus,
    FullySynchronousSpikeStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    HyperpolarizingCurrentClampStimulus,
    LinearCurrentClampSomaticStimulus,
    LinearCurrentClampStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    MultiPulseCurrentClampStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampStimulus,
    PoissonSpikeStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeConstantCurrentClampStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SinusoidalCurrentClampStimulus,
    SinusoidalPoissonSpikeStimulus,
    SubthresholdCurrentClampSomaticStimulus,
    SubthresholdCurrentClampStimulus,
)

# Full stimulus union, including spike stimuli and deprecated somatic aliases
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
    | SinusoidalPoissonSpikeStimulus
    # --- deprecated somatic names for backward compat ---
    | ConstantCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | RelativeNormallyDistributedCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus,
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
    | SubthresholdCurrentClampStimulus
    # --- deprecated somatic names for backward compat ---
    | ConstantCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | RelativeNormallyDistributedCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus,
    Discriminator("type"),
]


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
