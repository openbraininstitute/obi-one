from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimuli.electric_field import (
    SpatiallyUniformElectricFieldStimulus,
    TemporallyCosineSpatiallyUniformElectricFieldStimulus,
)
from obi_one.scientific.blocks.stimuli.ornstein_uhlenbeck import (
    OrnsteinUhlenbeckConductanceSomaticStimulus,
    OrnsteinUhlenbeckCurrentSomaticStimulus,
    RelativeOrnsteinUhlenbeckConductanceSomaticStimulus,
    RelativeOrnsteinUhlenbeckCurrentSomaticStimulus,
)
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
    SEClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SinusoidalPoissonSpikeStimulus,
    SubthresholdCurrentClampSomaticStimulus,
)

_NONRELATIVE_INJECTION_STIMULI = (
    ConstantCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | OrnsteinUhlenbeckCurrentSomaticStimulus
    | OrnsteinUhlenbeckConductanceSomaticStimulus
)

_RELATIVE_INJECTION_STIMULI = (
    RelativeNormallyDistributedCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus
    | RelativeOrnsteinUhlenbeckCurrentSomaticStimulus
    | RelativeOrnsteinUhlenbeckConductanceSomaticStimulus
)

_INJECTION_STIMULI = _RELATIVE_INJECTION_STIMULI | _NONRELATIVE_INJECTION_STIMULI

_SPIKE_STIMULI = (
    PoissonSpikeStimulus | FullySynchronousSpikeStimulus | SinusoidalPoissonSpikeStimulus
)

_FIELD_STIMULI = (
    SpatiallyUniformElectricFieldStimulus | TemporallyCosineSpatiallyUniformElectricFieldStimulus
)

StimulusUnion = Annotated[
    _INJECTION_STIMULI | _SPIKE_STIMULI | SEClampSomaticStimulus,
    Discriminator("type"),
]

CircuitStimulusUnion = Annotated[
    _INJECTION_STIMULI | _SPIKE_STIMULI | _FIELD_STIMULI,
    Discriminator("type"),
]

MEModelStimulusUnion = Annotated[
    _INJECTION_STIMULI,
    Discriminator("type"),
]

IonChannelModelStimulusUnion = Annotated[
    _NONRELATIVE_INJECTION_STIMULI | SEClampSomaticStimulus,
    Discriminator("type"),
]


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
