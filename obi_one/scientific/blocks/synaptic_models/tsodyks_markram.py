import abc
import logging
from functools import partial
from math import isfinite
from typing import ClassVar, NamedTuple

from pandas import DataFrame
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    resolve_distribution,
)
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
)

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

    _synapse_model_family = "TM_model"

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
        },
    )

    fascilitation_time: AllDistributionsReference | None = Field(
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

    fascilitation_time_shared_within: bool = Field(
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

    def sample(self, indices: DataFrame) -> DataFrame:

        n = len(indices)

        def sample_from(
            parameter_name: str,
            attr: AllDistributionsReference | None,
            default: DistributionDefault,
        ) -> list[float]:
            samples = resolve_distribution(attr, default).sample_with_constraints(n)
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
                    self.fascilitation_time,
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
