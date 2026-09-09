import abc
import logging
from functools import partial
from math import isfinite
from typing import ClassVar, NamedTuple

import numpy as np
from pandas import DataFrame
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    resolve_distribution,
)
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.synaptic_models.base import (
    SynapseModelFamily,
    SynapticModelBase,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
)
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


class _ParameterDomain(NamedTuple):
    minimum: float | None = None
    maximum: float | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    integer: bool = False
    description: str = ""


_TM_PARAMETER_DOMAINS: dict[str, _ParameterDomain] = {
    "u_hill_coefficient": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive finite value",
    ),
    "conductance": _ParameterDomain(
        minimum=0.0,
        description="a non-negative finite value",
    ),
    "conductance_scale_factor": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive finite value",
    ),
    "facilitation_time": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive time in milliseconds",
    ),
    "depression_time": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive time in milliseconds",
    ),
    "n_rrp_vesicles": _ParameterDomain(
        minimum=1.0,
        integer=True,
        description="an integer value greater than or equal to 1",
    ),
    "decay_time": _ParameterDomain(
        minimum=0.0,
        minimum_inclusive=False,
        description="a positive time in milliseconds",
    ),
    "u_syn": _ParameterDomain(
        minimum=0.0,
        maximum=1.0,
        description="a finite value between 0 and 1",
    ),
    "delay": _ParameterDomain(
        minimum=0.0,
        description="a non-negative time in milliseconds",
    ),
}


def _is_valid_parameter_sample(sample: float, domain: _ParameterDomain) -> bool:
    value = float(sample)
    valid = isfinite(value)
    if valid and domain.integer:
        valid = value.is_integer()
    if valid and domain.minimum is not None:
        valid = value >= domain.minimum if domain.minimum_inclusive else value > domain.minimum
    if valid and domain.maximum is not None:
        valid = value <= domain.maximum if domain.maximum_inclusive else value < domain.maximum
    return valid


def _validate_parameter_samples(parameter_name: str, samples: list[float]) -> list[float]:
    domain = _TM_PARAMETER_DOMAINS[parameter_name]
    invalid_samples = [
        sample for sample in samples if not _is_valid_parameter_sample(sample, domain)
    ]

    if invalid_samples:
        msg = (
            f"Invalid values sampled for Tsodyks-Markram parameter {parameter_name!r}: "
            f"expected {domain.description}; got {invalid_samples[:3]!r}."
        )
        raise ValueError(msg)

    return samples


class TsodyksMarkramSynapticModel(SynapticModelBase, abc.ABC):
    """Tsodyks-Markram synaptic model with optional distribution references."""

    _synapse_model_family: ClassVar[SynapseModelFamily] = SynapseModelFamily.TSODYKS_MARKRAM

    u_hill_coefficient_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="U Hill Coefficient Distribution",
        description=(
            "Distribution of the Hill coefficient for the steady-state utilization of synaptic "
            "efficacy (u). If omitted, "
            f"{_DEFAULT_U_HILL_COEFFICIENT.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_U_HILL_COEFFICIENT.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.U_HILL_COEFFICIENT_DISTRIBUTION,
        },
    )

    conductance_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance (g_syn) Distribution",
        description=(
            "Distribution of synaptic conductance (g_syn). If omitted, "
            f"{_DEFAULT_CONDUCTANCE.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_CONDUCTANCE.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.CONDUCTANCE_DISTRIBUTION,
        },
    )

    conductance_scale_factor_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance Scale Factor Distribution",
        description=(
            "Distribution of the conductance scale factor that multiplies the synaptic "
            "conductance (g_syn) to allow for fitting of synaptic conductance values that are "
            "outside of the range of the conductance distribution. If omitted, "
            f"{_DEFAULT_CONDUCTANCE_SCALE_FACTOR.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_CONDUCTANCE_SCALE_FACTOR.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION,
        },
    )

    facilitation_time: AllDistributionsReference | None = Field(
        default=None,
        title="Facilitation Time Distribution",
        description=(
            "Distribution of facilitation time in milliseconds. If omitted, "
            f"{_DEFAULT_FACILITATION_TIME.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_FACILITATION_TIME.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.FACILITATION_TIME_DISTRIBUTION,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    depression_time: AllDistributionsReference | None = Field(
        default=None,
        title="Depression Time Distribution",
        description=(
            "Distribution of depression time in milliseconds. If omitted, "
            f"{_DEFAULT_DEPRESSION_TIME.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_DEPRESSION_TIME.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.DEPRESSION_TIME_DISTRIBUTION,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    n_rrp_vesicles_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Number of RRP Vesicles Distribution",
        description=(
            "Distribution of the number of readily releasable pool (RRP) vesicles. If omitted, "
            f"{_DEFAULT_N_RRP_VESICLES.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_N_RRP_VESICLES.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.N_RRP_VESICLES_DISTRIBUTION,
        },
    )

    decay_time: AllDistributionsReference | None = Field(
        default=None,
        title="Decay Time Distribution",
        description=(
            "Distribution of decay time in milliseconds. If omitted, "
            f"{_DEFAULT_DECAY_TIME.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_DECAY_TIME.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.DECAY_TIME_DISTRIBUTION,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    u_syn: AllDistributionsReference | None = Field(
        default=None,
        title="U_syn Distribution",
        description=(
            "Distribution of the utilization of synaptic efficacy (u_syn) for the first spike "
            "in a spike train. If omitted, "
            f"{_DEFAULT_U_SYN.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_U_SYN.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.U_SYN_DISTRIBUTION,
        },
    )

    delay_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Delay Distribution",
        description=(
            "Distribution for the synaptic delay from the presynaptic spike in milliseconds. "
            "If omitted, "
            f"{_DEFAULT_DELAY.description} is used."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_DELAY.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.DELAY_DISTRIBUTION,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    u_hill_coefficient_shared_within: bool = Field(
        default=False,
        title="U Hill Coefficient Shared Within",
        description="Whether the Hill coefficient for the steady-state utilization of synaptic"
        " efficacy (u) is shared within the synapses between the source and target"
        " neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    conductance_distribution_shared_within: bool = Field(
        default=False,
        title="Conductance (g_syn) Distribution Shared Within",
        description="Whether the synaptic conductance (g_syn) is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    conductance_scale_factor_distribution_shared_within: bool = Field(
        default=False,
        title="Conductance Scale Factor Distribution Shared Within",
        description="Whether the conductance scale factor distribution is shared within "
        "the synapses between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    facilitation_time_shared_within: bool = Field(
        default=False,
        title="Facilitation Time Distribution Shared Within",
        description="Whether the facilitation time is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    depression_time_shared_within: bool = Field(
        default=False,
        title="Depression Time Distribution Shared Within",
        description="Whether the depression time is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    n_rrp_vesicles_shared_within: bool = Field(
        default=False,
        title="Number of RRP Vesicles Distribution Shared Within",
        description="Whether the number of RRP vesicles is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    decay_time_shared_within: bool = Field(
        default=False,
        title="Decay Time Distribution Shared Within",
        description="Whether the decay time is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    u_syn_shared_within: bool = Field(
        default=False,
        title="U_syn Distribution Shared Within",
        description="Whether the utilization of synaptic efficacy (u_syn) for the first spike "
        "in a spike train is shared within the synapses between the source "
        "and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    delay_shared_within: bool = Field(
        default=False,
        title="Delay Distribution Shared Within",
        description="Whether the synaptic delay is shared within the synapses between the source "
        "and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_HIDDEN: True,
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    @property
    def cov_mat(self) -> list:
        return []

    @property
    def cov_dict(self) -> dict:
        return {}

    @classmethod
    def parameter_names(cls) -> list[str]:
        return [
            "u_hill_coefficient",
            "conductance",
            "conductance_scale_factor",
            "facilitation_time",
            "depression_time",
            "n_rrp_vesicles",
            "decay_time",
            "u_syn",
            "delay",
            "syn_type_id",
        ]

    @property
    @abc.abstractmethod
    def syn_type_id(self) -> int:
        """SONATA ``syn_type_id`` assigned to these synapses (distinguishes E/I models)."""

    def sample(self, indices: DataFrame, rng: np.random.Generator | None = None) -> DataFrame:

        n = len(indices)

        def sample_from(
            parameter_name: str,
            attr: AllDistributionsReference | None,
            default: DistributionDefault,
        ) -> list[float]:
            samples = resolve_distribution(attr, default).sample_with_constraints(n, rng=rng)
            return _validate_parameter_samples(parameter_name, samples)

        # TODO: 'shared_within' is currently ignored
        return DataFrame(
            {
                "u_hill_coefficient": sample_from(
                    "u_hill_coefficient",
                    self.u_hill_coefficient_distribution,
                    _DEFAULT_U_HILL_COEFFICIENT,
                ),
                "conductance": sample_from(
                    "conductance",
                    self.conductance_distribution,
                    _DEFAULT_CONDUCTANCE,
                ),
                "conductance_scale_factor": sample_from(
                    "conductance_scale_factor",
                    self.conductance_scale_factor_distribution,
                    _DEFAULT_CONDUCTANCE_SCALE_FACTOR,
                ),
                "facilitation_time": sample_from(
                    "facilitation_time",
                    self.facilitation_time,
                    _DEFAULT_FACILITATION_TIME,
                ),
                "depression_time": sample_from(
                    "depression_time",
                    self.depression_time,
                    _DEFAULT_DEPRESSION_TIME,
                ),
                "n_rrp_vesicles": sample_from(
                    "n_rrp_vesicles",
                    self.n_rrp_vesicles_distribution,
                    _DEFAULT_N_RRP_VESICLES,
                ),
                "decay_time": sample_from(
                    "decay_time",
                    self.decay_time,
                    _DEFAULT_DECAY_TIME,
                ),
                "u_syn": sample_from(
                    "u_syn",
                    self.u_syn,
                    _DEFAULT_U_SYN,
                ),
                "delay": sample_from(
                    "delay",
                    self.delay_distribution,
                    _DEFAULT_DELAY,
                ),
                "syn_type_id": [self.syn_type_id] * n,
            },
            index=indices.index,
        )


class ExcitatoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    """Tsodyks-Markram model of short-term plasticity at excitatory chemical synapses.

    It models how presynaptic activity changes synaptic efficacy through utilization and
    recovery of a finite pool of synaptic resources, capturing facilitation and depression.

    Original model: Tsodyks & Markram (1997)
    https://doi.org/10.1073/pnas.94.2.719
    """

    title: ClassVar[str] = "Excitatory Tsodyks-Markram"

    @property
    def syn_type_id(self) -> int:
        return 113  # 128, 130, 114, 123 are other values in edges files


class InhibitoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    """Tsodyks-Markram model of short-term plasticity at inhibitory chemical synapses.

    It models how presynaptic activity changes synaptic efficacy through utilization and
    recovery of a finite pool of synaptic resources, capturing facilitation and depression.

    Original model: Tsodyks & Markram (1997)
    https://doi.org/10.1073/pnas.94.2.719
    """

    title: ClassVar[str] = "Inhibitory Tsodyks-Markram"

    @property
    def syn_type_id(self) -> int:
        return 7  # smaller than 100
