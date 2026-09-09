"""The distribution each Tsodyks-Markram parameter falls back to when left unset.

Kept apart from the block so the values and the model that samples them can be read separately:
this file is the science, `block.py` the pydantic surface around it, and `domains.py` the range
each of these values has to stay inside.
"""

import logging
from functools import partial

from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.defaults import DistributionDefault
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution

L = logging.getLogger(__name__)

_DEFAULT_U_HILL_COEFFICIENT = DistributionDefault(partial(FloatConstantDistribution, value=1.94))
_DEFAULT_CONDUCTANCE = DistributionDefault(partial(GammaDistribution, shape=4.0, scale=0.25))
_DEFAULT_CONDUCTANCE_SCALE_FACTOR = DistributionDefault(
    partial(FloatConstantDistribution, value=0.7)
)
_DEFAULT_FACILITATION_TIME = DistributionDefault(
    partial(GammaDistribution, shape=11.56, scale=1.4706)
)
_DEFAULT_DEPRESSION_TIME = DistributionDefault(
    partial(GammaDistribution, shape=1995.11, scale=0.3358)
)
_DEFAULT_N_RRP_VESICLES = DistributionDefault(
    partial(
        IntDiscreteDistribution,
        values=(1, 2, 3, 4, 5),
        probabilities=(0.3, 0.3, 0.2, 0.1, 0.1),
    )
)
_DEFAULT_DECAY_TIME = DistributionDefault(
    partial(NormalDistribution, min=1.7, max=1.9, mean=1.7, standard_deviation=0.1)
)
_DEFAULT_U_SYN = DistributionDefault(
    partial(NormalDistribution, min=0.2, max=0.7, mean=0.5, standard_deviation=0.25)
)
_DEFAULT_DELAY = DistributionDefault(
    partial(NormalDistribution, min=0.1, max=5.0, mean=2.0, standard_deviation=1.0)
)
