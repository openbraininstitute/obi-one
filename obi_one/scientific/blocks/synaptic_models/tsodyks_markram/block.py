"""The Tsodyks-Markram synaptic model: its parameters, their domains, and sampling."""

import abc
import logging
from functools import partial
from typing import ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
)
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.synaptic_models.base import (
    SynapseModelFamily,
    SynapticModelBase,
)
from obi_one.scientific.blocks.synaptic_models.domains import (
    ParameterDomain,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

L = logging.getLogger(__name__)


class TsodyksMarkramSynapticModel(SynapticModelBase, abc.ABC):
    """Tsodyks-Markram synaptic model with optional distribution references."""

    _synapse_model_family: ClassVar[SynapseModelFamily] = SynapseModelFamily.TSODYKS_MARKRAM

    u_hill_coefficient_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="U Hill Coefficient Distribution",
        description=(
            "Distribution of the Hill coefficient for the steady-state utilization of synaptic "
            "efficacy (u)."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "u_hill_coefficient",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive finite value"
            )._asdict(),
        },
    )

    conductance_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance (g_syn) Distribution",
        description="Distribution of synaptic conductance (g_syn).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "conductance",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, description="a non-negative finite value"
            )._asdict(),
        },
    )

    conductance_scale_factor_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance Scale Factor Distribution",
        description=(
            "Distribution of the conductance scale factor that multiplies the synaptic "
            "conductance (g_syn) to allow for fitting of synaptic conductance values that are "
            "outside of the range of the conductance distribution."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "conductance_scale_factor",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive finite value"
            )._asdict(),
        },
    )

    facilitation_time: AllDistributionsReference | None = Field(
        default=None,
        title="Facilitation Time Distribution",
        description="Distribution of facilitation time in milliseconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "facilitation_time",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive time in milliseconds"
            )._asdict(),
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    depression_time: AllDistributionsReference | None = Field(
        default=None,
        title="Depression Time Distribution",
        description="Distribution of depression time in milliseconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "depression_time",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive time in milliseconds"
            )._asdict(),
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    n_rrp_vesicles_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Number of RRP Vesicles Distribution",
        description="Distribution of the number of readily releasable pool (RRP) vesicles.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "n_rrp_vesicles",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=1.0, integer=True, description="an integer value greater than or equal to 1"
            )._asdict(),
        },
    )

    decay_time: AllDistributionsReference | None = Field(
        default=None,
        title="Decay Time Distribution",
        description="Distribution of decay time in milliseconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "decay_time",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive time in milliseconds"
            )._asdict(),
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    u_syn: AllDistributionsReference | None = Field(
        default=None,
        title="U_syn Distribution",
        description=(
            "Distribution of the utilization of synaptic efficacy (u_syn) for the first spike "
            "in a spike train."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "u_syn",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, maximum=1.0, description="a finite value between 0 and 1"
            )._asdict(),
        },
    )

    delay_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Delay Distribution",
        description=(
            "Distribution for the synaptic delay from the presynaptic spike in milliseconds. "
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SAMPLED_PARAMETER: "delay",
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, description="a non-negative time in milliseconds"
            )._asdict(),
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


class ExcitatoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    """Tsodyks-Markram model of short-term plasticity at excitatory chemical synapses.

    It models how presynaptic activity changes synaptic efficacy through utilization and
    recovery of a finite pool of synaptic resources, capturing facilitation and depression.

    Original model: Tsodyks & Markram (1997)
    https://doi.org/10.1073/pnas.94.2.719
    """

    title: ClassVar[str] = "Excitatory Tsodyks-Markram"

    # The distribution each parameter falls back to, and the role it answers. Declared here
    # rather than shared with the inhibitory model because the two take different values.
    _parameter_defaults: ClassVar[dict[ReferenceTag, tuple[str, DistributionDefault]]] = {
        ReferenceTag.EXCITATORY_U_HILL_COEFFICIENT_DISTRIBUTION: (
            "u_hill_coefficient_distribution",
            DistributionDefault(partial(FloatConstantDistribution, value=1.94)),
        ),
        ReferenceTag.EXCITATORY_CONDUCTANCE_DISTRIBUTION: (
            "conductance_distribution",
            DistributionDefault(partial(GammaDistribution, shape=4.0, scale=0.25)),
        ),
        ReferenceTag.EXCITATORY_CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION: (
            "conductance_scale_factor_distribution",
            DistributionDefault(partial(FloatConstantDistribution, value=0.7)),
        ),
        ReferenceTag.EXCITATORY_FACILITATION_TIME_DISTRIBUTION: (
            "facilitation_time",
            DistributionDefault(partial(GammaDistribution, shape=11.56, scale=1.4706)),
        ),
        ReferenceTag.EXCITATORY_DEPRESSION_TIME_DISTRIBUTION: (
            "depression_time",
            DistributionDefault(partial(GammaDistribution, shape=1995.11, scale=0.3358)),
        ),
        ReferenceTag.EXCITATORY_N_RRP_VESICLES_DISTRIBUTION: (
            "n_rrp_vesicles_distribution",
            DistributionDefault(
                partial(
                    IntDiscreteDistribution,
                    values=(1, 2, 3, 4, 5),
                    probabilities=(0.3, 0.3, 0.2, 0.1, 0.1),
                )
            ),
        ),
        ReferenceTag.EXCITATORY_DECAY_TIME_DISTRIBUTION: (
            "decay_time",
            DistributionDefault(
                partial(NormalDistribution, min=1.7, max=1.9, mean=1.7, standard_deviation=0.1)
            ),
        ),
        ReferenceTag.EXCITATORY_U_SYN_DISTRIBUTION: (
            "u_syn",
            DistributionDefault(
                partial(NormalDistribution, min=0.2, max=0.7, mean=0.5, standard_deviation=0.25)
            ),
        ),
        ReferenceTag.EXCITATORY_DELAY_DISTRIBUTION: (
            "delay_distribution",
            DistributionDefault(
                partial(NormalDistribution, min=0.1, max=5.0, mean=2.0, standard_deviation=1.0)
            ),
        ),
    }

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

    # As above, for inhibitory synapses. Only the conductance differs so far - the figure
    # the example notebook uses for inhibitory connections. The other eight still carry
    # the excitatory values and want replacing with measured ones.
    _parameter_defaults: ClassVar[dict[ReferenceTag, tuple[str, DistributionDefault]]] = {
        ReferenceTag.INHIBITORY_U_HILL_COEFFICIENT_DISTRIBUTION: (
            "u_hill_coefficient_distribution",
            DistributionDefault(partial(FloatConstantDistribution, value=1.94)),
        ),
        ReferenceTag.INHIBITORY_CONDUCTANCE_DISTRIBUTION: (
            "conductance_distribution",
            DistributionDefault(partial(GammaDistribution, shape=8.0, scale=0.25)),
        ),
        ReferenceTag.INHIBITORY_CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION: (
            "conductance_scale_factor_distribution",
            DistributionDefault(partial(FloatConstantDistribution, value=0.7)),
        ),
        ReferenceTag.INHIBITORY_FACILITATION_TIME_DISTRIBUTION: (
            "facilitation_time",
            DistributionDefault(partial(GammaDistribution, shape=11.56, scale=1.4706)),
        ),
        ReferenceTag.INHIBITORY_DEPRESSION_TIME_DISTRIBUTION: (
            "depression_time",
            DistributionDefault(partial(GammaDistribution, shape=1995.11, scale=0.3358)),
        ),
        ReferenceTag.INHIBITORY_N_RRP_VESICLES_DISTRIBUTION: (
            "n_rrp_vesicles_distribution",
            DistributionDefault(
                partial(
                    IntDiscreteDistribution,
                    values=(1, 2, 3, 4, 5),
                    probabilities=(0.3, 0.3, 0.2, 0.1, 0.1),
                )
            ),
        ),
        ReferenceTag.INHIBITORY_DECAY_TIME_DISTRIBUTION: (
            "decay_time",
            DistributionDefault(
                partial(NormalDistribution, min=1.7, max=1.9, mean=1.7, standard_deviation=0.1)
            ),
        ),
        ReferenceTag.INHIBITORY_U_SYN_DISTRIBUTION: (
            "u_syn",
            DistributionDefault(
                partial(NormalDistribution, min=0.2, max=0.7, mean=0.5, standard_deviation=0.25)
            ),
        ),
        ReferenceTag.INHIBITORY_DELAY_DISTRIBUTION: (
            "delay_distribution",
            DistributionDefault(
                partial(NormalDistribution, min=0.1, max=5.0, mean=2.0, standard_deviation=1.0)
            ),
        ),
    }

    @property
    def syn_type_id(self) -> int:
        return 7  # smaller than 100
