from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.stimuli.electric_field import (
    SpatiallyUniformElectricFieldStimulus,
    TemporallyCosineSpatiallyUniformElectricFieldStimulus,
)
from obi_one.scientific.blocks.stimuli.ornstein_uhlenbeck import (
    OrnsteinUhlenbeckConductanceStimulus,
    OrnsteinUhlenbeckCurrentStimulus,
    RelativeOrnsteinUhlenbeckConductanceStimulus,
    RelativeOrnsteinUhlenbeckCurrentStimulus,
)
from obi_one.scientific.blocks.stimuli.spike import (
    FullySynchronousSpikeStimulus,
    PoissonSpikeStimulus,
    SinusoidalPoissonSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.spike.isi_distribution import (
    InterSpikeIntervalDistributionSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.spike.time_distribution import (
    SpikeTimeDistributionSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampStimulus,
    HyperpolarizingCurrentClampStimulus,
    LinearCurrentClampStimulus,
    MultiLevelSEClampSomaticStimulus,
    MultiPulseCurrentClampStimulus,
    NormallyDistributedCurrentClampStimulus,
    RelativeConstantCurrentClampStimulus,
    RelativeLinearCurrentClampStimulus,
    RelativeNormallyDistributedCurrentClampStimulus,
    SEClampSomaticStimulus,
    SinusoidalCurrentClampStimulus,
    SubthresholdCurrentClampStimulus,
)

_ABSOLUTE_INJECTION_STIMULI = (
    ConstantCurrentClampStimulus
    | HyperpolarizingCurrentClampStimulus
    | LinearCurrentClampStimulus
    | MultiPulseCurrentClampStimulus
    | NormallyDistributedCurrentClampStimulus
    | SinusoidalCurrentClampStimulus
    | OrnsteinUhlenbeckCurrentStimulus
    | OrnsteinUhlenbeckConductanceStimulus
)

_RELATIVE_INJECTION_STIMULI = (
    RelativeNormallyDistributedCurrentClampStimulus
    | RelativeConstantCurrentClampStimulus
    | RelativeLinearCurrentClampStimulus
    | SubthresholdCurrentClampStimulus
    | RelativeOrnsteinUhlenbeckCurrentStimulus
    | RelativeOrnsteinUhlenbeckConductanceStimulus
)

_INJECTION_STIMULI = _RELATIVE_INJECTION_STIMULI | _ABSOLUTE_INJECTION_STIMULI

_SPIKE_STIMULI = (
    PoissonSpikeStimulus
    | FullySynchronousSpikeStimulus
    | SinusoidalPoissonSpikeStimulus
    | InterSpikeIntervalDistributionSpikeStimulus
    | SpikeTimeDistributionSpikeStimulus
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
