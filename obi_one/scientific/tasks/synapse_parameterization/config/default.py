"""What each unset reference in the synapse parameterization config resolves to.

One spec per role, from which both the schema the UI reads and the references the fill pass
substitutes are derived - so a name cannot drift from the block it names.
"""

import logging

from obi_one.core.fill_none_references import BlockDefault
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    tsodyks_markram_default_distributions,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.synaptic_models import SynapticModelReference

L = logging.getLogger(__name__)

DEFAULT_SYNAPTIC_MODEL_NAME = "Default: Excitatory Tsodyks-Markram"

# One entry per role a reference field can play in this config: the reference type to build
# (which has to match the field's own union), the dictionary the block is registered in, the
# name it takes there, and a factory for the block itself. Both the schema the UI reads and the
# references the fill pass substitutes are derived from this, so they cannot disagree.
_DEFAULTS: dict[str, BlockDefault] = {
    ReferenceTag.SYNAPTIC_MODEL: BlockDefault(
        SynapticModelReference,
        "synaptic_models",
        DEFAULT_SYNAPTIC_MODEL_NAME,
        ExcitatoryTsodyksMarkramSynapticModel,
    ),
    # "No restriction" for the assigner roles: an inter- or presynaptic assigner naming neither
    # end then behaves like the all-pairs one, which is what placing no restriction means.
    # Biophysical because that is what a chemical edge population connects in the normal case,
    # and because there is no atomic non-virtual reference type to carry a broader default. An
    # edge population on point or virtual neurons has to name its ends, and the assigner's own
    # validation says which one does not fit.
    ReferenceTag.SYNAPSE_ASSIGNMENT_SOURCE: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.SYNAPSE_ASSIGNMENT_TARGET: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    # Every neuron of the combined set's own type. One entry per type because each combined
    # subclass redeclares its operands with its own reference union.
    ReferenceTag.ANY_NEURON_SET_OPERAND: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.NON_VIRTUAL_NEURON_SET_OPERAND: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.BIOPHYSICAL_NEURON_SET_OPERAND: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.POINT_NEURON_SET_OPERAND: BlockDefault(
        PointNeuronSetReference,
        "neuron_sets",
        "Default: All Point Neurons",
        AllPointNeurons,
    ),
    ReferenceTag.VIRTUAL_NEURON_SET_OPERAND: BlockDefault(
        VirtualNeuronSetReference,
        "neuron_sets",
        "Default: All Virtual Neurons",
        AllVirtualNeurons,
    ),
}


def _distribution_defaults() -> dict[str, BlockDefault]:
    """The nine Tsodyks-Markram parameters, in the same shape as `_DEFAULTS`."""
    return {
        tag: BlockDefault(
            AllDistributionsReference, "distributions", name, lambda d=distribution: d
        )
        for tag, (name, distribution) in tsodyks_markram_default_distributions().items()
    }


def default_blocks() -> dict[str, BlockDefault]:
    """Every role this config answers: the nine parameters, plus the rest declared above."""
    return {**_distribution_defaults(), **_DEFAULTS}
