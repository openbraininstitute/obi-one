"""Discriminated union types for Brian2-compatible blocks.

Only includes stimulus and recording types that are supported by the Brian2
simulator with point neuron models.
"""

from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.blocks.recording import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus
from obi_one.scientific.blocks.stimuli.ornstein_uhlenbeck import (
    OrnsteinUhlenbeckCurrentSomaticStimulus,
)
from obi_one.scientific.blocks.stimuli.spike import (
    FullySynchronousSpikeStimulus,
    PoissonSpikeStimulus,
    SinusoidalPoissonSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NormallyDistributedCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
)

_BRIAN2_INJECTION_STIMULI = (
    ConstantCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | NormallyDistributedCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | OrnsteinUhlenbeckCurrentSomaticStimulus
)

_BRIAN2_SPIKE_STIMULI = (
    PoissonSpikeStimulus | FullySynchronousSpikeStimulus | SinusoidalPoissonSpikeStimulus
)

Brian2CircuitStimulusUnion = Annotated[
    _BRIAN2_INJECTION_STIMULI | _BRIAN2_SPIKE_STIMULI | Brian2DirectPoissonStimulus,
    Discriminator("type"),
]

Brian2RecordingUnion = Annotated[
    SomaVoltageRecording | TimeWindowSomaVoltageRecording,
    Discriminator("type"),
]
