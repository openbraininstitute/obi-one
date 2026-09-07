"""Explicit fallback synaptic models, one per synapse model family.

Synapse parameterization builds a single parameter table per edge population and
then lets each assigner overwrite the rows it owns, so every synapse that no
assigner claims keeps the values the table was filled with. Whichever model does
that filling therefore decides the biology of the unclaimed synapses - including
their ``syn_type_id`` - which is too consequential to be left to whichever model
the configuration happened to list first. Each family names its default here.
"""

from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)

DEFAULT_SYNAPTIC_MODELS: dict[str, type[SynapticModelBase]] = {
    # Excitatory for every Tsodyks-Markram subclass. An unclaimed synapse has to be given
    # some syn_type_id, and excitatory synapses outnumber inhibitory ones in the circuits
    # this runs on, so the excitatory model leaves the fewest of them misparameterized.
    TsodyksMarkramSynapticModel.synapse_model_family(): ExcitatoryTsodyksMarkramSynapticModel,
}


def default_synaptic_model_for(model: SynapticModelBase) -> SynapticModelBase:
    """Create the default synaptic model for the family `model` belongs to.

    A fresh instance every call: the caller samples from it, and the models carry
    per-instance distribution references rather than being interchangeable singletons.
    """
    family = type(model).synapse_model_family()
    default_class = DEFAULT_SYNAPTIC_MODELS.get(family)
    if default_class is None:
        msg = (
            f"No default synaptic model is registered for synapse model family {family!r}. "
            "Every family MUST register one in DEFAULT_SYNAPTIC_MODELS, because the synapses "
            "that no assigner covers are parameterized from it."
        )
        raise NotImplementedError(msg)
    return default_class()
