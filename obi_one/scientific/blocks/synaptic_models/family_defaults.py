"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.synaptic_models.family_defaults import (
    default_synaptic_model_for,
    DEFAULT_SYNAPTIC_MODELS,
    ExcitatoryTsodyksMarkramSynapticModel,
    SynapseModelFamily,
    SynapticModelBase,
)

__all__ = [
    "default_synaptic_model_for",
    "DEFAULT_SYNAPTIC_MODELS",
    "ExcitatoryTsodyksMarkramSynapticModel",
    "SynapseModelFamily",
    "SynapticModelBase",
]
