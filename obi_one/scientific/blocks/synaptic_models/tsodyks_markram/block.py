"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import]

from obi_one_lazy.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    abc,
    AllDistributionsReference,
    ClassVar,
    DistributionDefault,
    ExcitatoryTsodyksMarkramSynapticModel,
    Field,
    FloatConstantDistribution,
    GammaDistribution,
    InhibitoryTsodyksMarkramSynapticModel,
    IntDiscreteDistribution,
    L,
    logging,
    NormalDistribution,
    ParameterDomain,
    partial,
    ReferenceTag,
    SchemaKey,
    SynapseModelFamily,
    SynapticModelBase,
    TsodyksMarkramSynapticModel,
    UIElement,
    Units,
)
