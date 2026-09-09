"""Tsodyks-Markram synaptic models.

Split so the defaults can be read on their own; the module's public names are unchanged, so
`from ...synaptic_models.tsodyks_markram import X` keeps working wherever it was already used.
"""

from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.distributions import (
    TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS,
    tsodyks_markram_default_distributions,
)

__all__ = [
    "TSODYKS_MARKRAM_REFERENCE_TAG_DEFAULTS",
    "ExcitatoryTsodyksMarkramSynapticModel",
    "InhibitoryTsodyksMarkramSynapticModel",
    "TsodyksMarkramSynapticModel",
    "tsodyks_markram_default_distributions",
]
