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
from obi_one.scientific.blocks.stimuli.spike import (
    FullySynchronousSpikeStimulus,
    PoissonSpikeStimulus,
    SinusoidalPoissonSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiLevelSEClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    RelativeNormallyDistributedCurrentClampSomaticStimulus,
    SEClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SubthresholdCurrentClampSomaticStimulus,
)

_ABSOLUTE_INJECTION_STIMULI = (
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

_INJECTION_STIMULI = _RELATIVE_INJECTION_STIMULI | _ABSOLUTE_INJECTION_STIMULI

_SPIKE_STIMULI = (
    PoissonSpikeStimulus | FullySynchronousSpikeStimulus | SinusoidalPoissonSpikeStimulus
)

_FIELD_STIMULI = (
    SpatiallyUniformElectricFieldStimulus | TemporallyCosineSpatiallyUniformElectricFieldStimulus
)

StimulusUnion = Annotated[
    _INJECTION_STIMULI | _SPIKE_STIMULI,
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
    SEClampSomaticStimulus | MultiLevelSEClampSomaticStimulus | _ABSOLUTE_INJECTION_STIMULI,
    Discriminator("type"),
]


class StimulusReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = StimulusUnion
