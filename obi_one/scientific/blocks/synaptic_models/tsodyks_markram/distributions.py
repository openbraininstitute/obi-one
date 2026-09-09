"""The distribution each Tsodyks-Markram parameter falls back to when left unset.

Kept apart from the block so that the values and the model that samples them can be read
separately: this file is the science, `block.py` the pydantic surface around it.
"""

import logging
from functools import partial

from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.defaults import DistributionDefault
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

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


# What each parameter's reference field shows when left unset, keyed by the role the
# field plays. Built from the same DistributionDefault objects `sample` falls back to, so
# the label and the distribution it names cannot drift apart.
_TSODYKS_MARKRAM_DEFAULTS: dict[str, DistributionDefault] = {
    ReferenceTag.U_HILL_COEFFICIENT_DISTRIBUTION: _DEFAULT_U_HILL_COEFFICIENT,
    ReferenceTag.CONDUCTANCE_DISTRIBUTION: _DEFAULT_CONDUCTANCE,
    ReferenceTag.CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION: _DEFAULT_CONDUCTANCE_SCALE_FACTOR,
    ReferenceTag.FACILITATION_TIME_DISTRIBUTION: _DEFAULT_FACILITATION_TIME,
    ReferenceTag.DEPRESSION_TIME_DISTRIBUTION: _DEFAULT_DEPRESSION_TIME,
    ReferenceTag.N_RRP_VESICLES_DISTRIBUTION: _DEFAULT_N_RRP_VESICLES,
    ReferenceTag.DECAY_TIME_DISTRIBUTION: _DEFAULT_DECAY_TIME,
    ReferenceTag.U_SYN_DISTRIBUTION: _DEFAULT_U_SYN,
    ReferenceTag.DELAY_DISTRIBUTION: _DEFAULT_DELAY,
}

# What each parameter's reference field resolves to when left unset, keyed by role: the name
# the block is registered under once a config is filled, and the block itself. Both together so
# the UI can show the name and read the distribution behind it - offering the parameters in a
# tooltip, or materialising it when someone wants to edit the default rather than accept it.
TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS: dict[str, dict] = {
    tag: {"name": default.label, "block": default.create().model_dump(mode="json")}
    for tag, default in _TSODYKS_MARKRAM_DEFAULTS.items()
}


def tsodyks_markram_default_distributions() -> dict[str, tuple[str, Distribution]]:
    """The block each parameter's reference resolves to when left unset, keyed by role.

    Returns one (block name, distribution) pair per tag. The name is the label the UI already
    shows for that field, so the option a user picked and the block that appears in the config
    once it is filled carry the same text. Fresh instances every call: they are registered into
    a config, which must not share blocks with another.
    """
    return {
        tag: (default.label, default.create()) for tag, default in _TSODYKS_MARKRAM_DEFAULTS.items()
    }
