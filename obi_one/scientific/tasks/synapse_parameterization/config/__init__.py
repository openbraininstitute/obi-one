"""Synapse parameterization configuration.

A package rather than a module so the public names survive however the code inside is
arranged; every existing import of this module keeps working.
"""

from obi_one.scientific.tasks.synapse_parameterization.config.config import (
    DEFAULT_SYNAPTIC_MODEL_NAME,
    BlockGroup,
    SynapseParameterizationScanConfig,
    SynapseParameterizationSingleConfig,
)

__all__ = [
    "DEFAULT_SYNAPTIC_MODEL_NAME",
    "BlockGroup",
    "SynapseParameterizationScanConfig",
    "SynapseParameterizationSingleConfig",
]
