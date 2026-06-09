from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus

Brian2CircuitStimulusUnion = Annotated[
    Brian2DirectPoissonStimulus,
    Discriminator("type"),
]
