import abc
import logging

from pandas import DataFrame
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
)

L = logging.getLogger(__name__)


class TsodyksMarkramSynapticModel(SynapticModelBase, abc.ABC):
    _synapse_model_family = "TM_model"

    u_hill_coefficient_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="U Hill Coefficient Distribution",
        description="Distribution of the Hill coefficient for the steady-state utilization"
        " of synaptic efficacy (u).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    conductance_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance (g_syn) Distribution",
        description="Distribution of synaptic conductance (g_syn).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    conductance_scale_factor_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance Scale Factor Distribution",
        description="Distribution of the conductance scale factor that multiplies the synaptic "
        "conductance (g_syn) to allow for fitting of synaptic conductance values that are "
        "outside of the range of the conductance distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    fascilitation_time: AllDistributionsReference | None = Field(
        default=None,
        title="Fascilitation Time Distribution",
        description="Fascilitation Time Distribution",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    depression_time: AllDistributionsReference | None = Field(
        default=None,
        title="Depression Time Distribution",
        description="Depression Time Distribution",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    n_rrp_vesicles_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Number of RRP Vesicles Distribution",
        description="Distribution of the number of readily releasable pool (RRP) vesicles.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    decay_time: AllDistributionsReference | None = Field(
        default=None,
        title="Decay Time Distribution",
        description="Decay Time Distribution",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    u_syn: AllDistributionsReference | None = Field(
        default=None,
        title="U_syn Distribution",
        description="Distribution of the utilization of synaptic efficacy (u_syn) for "
        "the first spike in a spike train.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    delay_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Delay distribution",
        description="Distribution for the synaptic delay (from the presyn spike).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
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
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    conductance_distribution_shared_within: bool = Field(
        default=False,
        title="Conductance (g_syn) Distribution Shared Within",
        description="Whether the synaptic conductance (g_syn) is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    conductance_scale_factor_distribution_shared_within: bool = Field(
        default=False,
        title="Conductance Scale Factor Distribution Shared Within",
        description="Whether the conductance scale factor distribution is shared within "
        "the synapses between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    fascilitation_time_shared_within: bool = Field(
        default=False,
        title="Fascilitation Time Distribution Shared Within",
        description="Whether the fascilitation time is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    depression_time_shared_within: bool = Field(
        default=False,
        title="Depression Time Distribution Shared Within",
        description="Whether the depression time is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    n_rrp_vesicles_shared_within: bool = Field(
        default=False,
        title="Number of RRP Vesicles Distribution Shared Within",
        description="Whether the number of RRP vesicles is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    decay_time_shared_within: bool = Field(
        default=False,
        title="Decay Time Distribution Shared Within",
        description="Whether the decay time is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
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
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    delay_shared_within: bool = Field(
        default=False,
        title="Delay Distribution Shared Within",
        description="Whether the synaptic delay is shared within the synapses between the source "
        "and target neuron sets.",
        json_schema_extra={
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

        def resolve(attr: AllDistributionsReference | None, default: Distribution) -> list[float]:
            distribution = default if attr is None else attr.block
            return distribution.sample_with_constraints(n)

        # TODO: 'shared_within' is currently ignored
        return DataFrame(
            {
                "u_hill_coefficient": resolve(
                    self.u_hill_coefficient_distribution,
                    FloatConstantDistribution(value=1.94),
                ),
                "conductance": resolve(
                    self.conductance_distribution,
                    GammaDistribution(shape=4.0, scale=0.25),
                ),
                "conductance_scale_factor": resolve(
                    self.conductance_scale_factor_distribution,
                    FloatConstantDistribution(value=0.7),
                ),
                "facilitation_time": resolve(
                    self.fascilitation_time,
                    GammaDistribution(shape=11.56, scale=1.4706),
                ),
                "depression_time": resolve(
                    self.depression_time,
                    GammaDistribution(shape=1995.11, scale=0.3358),
                ),
                "n_rrp_vesicles": resolve(
                    self.n_rrp_vesicles_distribution,
                    IntDiscreteDistribution(
                        values=(1, 2, 3, 4, 5),
                        probabilities=(0.3, 0.3, 0.2, 0.1, 0.1),
                    ),
                ),
                "decay_time": resolve(
                    self.decay_time,
                    NormalDistribution(min=1.7, max=1.9, mean=1.7, standard_deviation=0.1),
                ),
                "u_syn": resolve(
                    self.u_syn,
                    NormalDistribution(min=0.2, max=0.7, mean=0.5, standard_deviation=0.25),
                ),
                "delay": resolve(
                    self.delay_distribution,
                    NormalDistribution(min=0.1, max=5.0, mean=2.0, standard_deviation=1.0),
                ),
                "syn_type_id": [self.syn_type_id] * n,
            },
            index=indices.index,
        )


class ExcitatoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    @property
    def syn_type_id(self) -> int:
        return 113  # 128, 130, 114, 123 are other values in edges files


class InhibitoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    @property
    def syn_type_id(self) -> int:
        return 7  # smaller than 100
