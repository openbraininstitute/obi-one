from obi_one.scientific.simulation.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    HyperpolarizingCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    NoiseCurrentClampSomaticStimulus,
    PercentageNoiseCurrentClampSomaticStimulus,
    RelativeConstantCurrentClampSomaticStimulus,
    RelativeLinearCurrentClampSomaticStimulus,
    SinusoidalCurrentClampSomaticStimulus,
    SubthresholdCurrentClampSomaticStimulus,
    SynchronousSingleSpikeStimulus,
    PoissonSpikeStimulus
)

StimulusUnion = (
    SynchronousSingleSpikeStimulus
    | ConstantCurrentClampSomaticStimulus
    | LinearCurrentClampSomaticStimulus
    | RelativeConstantCurrentClampSomaticStimulus
    | MultiPulseCurrentClampSomaticStimulus
    | SinusoidalCurrentClampSomaticStimulus
    | SubthresholdCurrentClampSomaticStimulus
    | HyperpolarizingCurrentClampSomaticStimulus
    | NoiseCurrentClampSomaticStimulus
    | PercentageNoiseCurrentClampSomaticStimulus
    | RelativeLinearCurrentClampSomaticStimulus
    | PoissonSpikeStimulus
)
