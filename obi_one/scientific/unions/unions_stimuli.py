from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimulus import (
    # New unified stimulus classes
    ConstantCurrentClampStimulus,
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
    FullySynchronousSpikeStimulus,
    # Deprecated somatic aliases (backward compatibility)
    ConstantCurrentClampSomaticStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SubthresholdCurrentClampSomaticStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
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