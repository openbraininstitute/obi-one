"""Discriminated union types for NEST-compatible blocks.

Only includes stimulus and recording types that are supported by the NEST
simulator with point neuron models.
"""

from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.blocks.recording import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.blocks.stimuli.ornstein_uhlenbeck import (
    OrnsteinUhlenbeckCurrentSomaticStimulus,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    FullySynchronousSpikeStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    PoissonSpikeStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SinusoidalPoissonSpikeStimulus,
)

_NEST_INJECTION_STIMULI = (
    ConstantCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | OrnsteinUhlenbeckCurrentSomaticStimulus
)

_NEST_SPIKE_STIMULI = (
    PoissonSpikeStimulus | FullySynchronousSpikeStimulus | SinusoidalPoissonSpikeStimulus
)

NestCircuitStimulusUnion = Annotated[
    _NEST_INJECTION_STIMULI | _NEST_SPIKE_STIMULI,
    Discriminator("type"),
]

NestRecordingUnion = Annotated[
    SomaVoltageRecording | TimeWindowSomaVoltageRecording,
    Discriminator("type"),
]
