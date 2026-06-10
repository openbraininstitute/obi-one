import abc
import logging

from pandas import DataFrame
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
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

    usyn: AllDistributionsReference | None = Field(
        default=None,
        title="Usyn Distribution",
        description="Distribution of the utilization of synaptic efficacy (usyn) for "
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

    usyn_shared_within: bool = Field(
        default=False,
        title="Usyn Distribution Shared Within",
        description="Whether the utilization of synaptic efficacy (usyn) for the first spike "
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
    def cov_mat(self) -> dict:
        return []

    @property
    def cov_dict(self) -> dict:
        return {}

    @property
    def synapse_type_id(self) -> int:
        raise NotImplementedError("synapse_type_id must be implemented by subclasses")

    def u_hill_coefficient_dict(self) -> dict:
        d = self.u_hill_coefficient_distribution.resolve()
        d["shared_within"] = self.u_hill_coefficient_shared_within
        return d

    def conductance_distribution_dict(self) -> dict:
        d = self.conductance_distribution.resolve()
        d["shared_within"] = self.conductance_distribution_shared_within
        return d

    def conductance_scale_factor_distribution_dict(self) -> dict:
        d = self.conductance_scale_factor_distribution.resolve()
        d["shared_within"] = self.conductance_scale_factor_distribution_shared_within
        return d

    def fascilitation_time_dict(self) -> dict:
        d = self.fascilitation_time.resolve()
        d["shared_within"] = self.fascilitation_time_shared_within
        return d

    def depression_time_dict(self) -> dict:
        d = self.depression_time.resolve()
        d["shared_within"] = self.depression_time_shared_within
        return d

    def n_rrp_vesicles_dict(self) -> dict:
        d = self.n_rrp_vesicles_distribution.resolve()
        d["shared_within"] = self.n_rrp_vesicles_shared_within
        return d

    def decay_time_dict(self) -> dict:
        d = self.decay_time.resolve()
        d["shared_within"] = self.decay_time_shared_within
        return d

    def usyn_dict(self) -> dict:
        d = self.usyn.resolve()
        d["shared_within"] = self.usyn_shared_within
        return d

    def delay_dict(self) -> dict:
        d = self.delay_distribution.resolve()
        d["shared_within"] = self.delay_shared_within
        return d

    def parameter_dictionaries(self) -> dict:
        return {
            "u_hill_coefficient": self.u_hill_coefficient_dict(),
            "conductance": self.conductance_distribution_dict(),
            "conductance_scale_factor": self.conductance_scale_factor_distribution_dict(),
            "facilitation_time": self.fascilitation_time_dict(),
            "depression_time": self.depression_time_dict(),
            "n_rrp_vesicles": self.n_rrp_vesicles_dict(),
            "decay_time": self.decay_time_dict(),
            "usyn": self.usyn_dict(),
            "delay": self.delay_dict(),
            "syn_type_id": self.synapse_type_id,
        }

    @classmethod
    def synapse_model_family(cls):
        return "TM_model"

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
            "usyn",
            "delay",
            "synapse_type_id",
        ]

    def sample(self, indices: DataFrame) -> DataFrame:

        u_hill_coefficient_distribution = self.u_hill_coefficient_distribution
        conductance_distribution = self.conductance_distribution
        conductance_scale_factor_distribution = self.conductance_scale_factor_distribution
        fascilitation_time = self.fascilitation_time
        depression_time = self.depression_time
        n_rrp_vesicles_distribution = self.n_rrp_vesicles_distribution
        decay_time = self.decay_time
        usyn = self.usyn
        delay_distribution = self.delay_distribution

        if u_hill_coefficient_distribution is None:
            u_hill_coefficient_distribution = FloatConstantDistribution(value=1.94)
        else:
            u_hill_coefficient_distribution = self.u_hill_coefficient_distribution.block

        if conductance_distribution is None:
            conductance_distribution = GammaDistribution(shape=4.0, scale=0.25)
        else:
            conductance_distribution = self.conductance_distribution.block

        if conductance_scale_factor_distribution is None:
            conductance_scale_factor_distribution = FloatConstantDistribution(value=0.7)
        else:
            conductance_scale_factor_distribution = self.conductance_scale_factor_distribution.block

        if fascilitation_time is None:
            fascilitation_time = GammaDistribution(shape=11.56, scale=1.4706)
        else:
            fascilitation_time = self.fascilitation_time.block

        if depression_time is None:
            depression_time = GammaDistribution(shape=1995.11, scale=0.3358)
        else:
            depression_time = self.depression_time.block

        if n_rrp_vesicles_distribution is None:
            n_rrp_vesicles_distribution = IntDiscreteDistribution(
                values=(1, 2, 3, 4, 5), probabilities=(0.3, 0.3, 0.2, 0.1, 0.1)
            )
        else:
            n_rrp_vesicles_distribution = self.n_rrp_vesicles_distribution.block

        if decay_time is None:
            decay_time = NormalDistribution(min=1.7, max=1.9, mean=1.7, standard_deviation=0.1)
        else:
            decay_time = self.decay_time.block

        if delay_distribution is None:
            delay_distribution = NormalDistribution(
                min=0.1, max=5.0, mean=2.0, standard_deviation=1.0
            )
        else:
            delay_distribution = self.delay_distribution.block
        
        if usyn is None:
            usyn = NormalDistribution(min=0.2, max=0.7, mean=0.5, standard_deviation=0.25)
        else:
            usyn = self.usyn.block

        n = len(indices)
        # TODO: 'shared_within' is currently ignored
        return DataFrame(
            {
                "u_hill_coefficient": u_hill_coefficient_distribution.sample_with_constraints(
                    n
                ),
                "conductance": conductance_distribution.sample_with_constraints(n),
                "conductance_scale_factor": conductance_scale_factor_distribution.sample_with_constraints(
                    n
                ),
                "facilitation_time": fascilitation_time.sample_with_constraints(n),
                "depression_time": depression_time.sample_with_constraints(n),
                "n_rrp_vesicles": n_rrp_vesicles_distribution.sample_with_constraints(n),
                "decay_time": decay_time.sample_with_constraints(n),
                "usyn": usyn.sample_with_constraints(n),
                "delay": delay_distribution.sample_with_constraints(n),
                "synapse_type_id": [self.synapse_type_id] * n,
            },
            index=indices.index,
        )


class ExcitatoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    @property
    def synapse_type_id(self) -> int:
        return 113  # 128, 130, 114, 123 are other values in edges files


class InhibitoryTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    @property
    def synapse_type_id(self) -> int:
        return 7  # smaller than 100


"""
# CORRELATION_COEFFICIENT_FIELD = (
#     Annotated[
#         float,
#         Field(ge=-1.0, le=1.0),
#     ]
#     | Annotated[
#         list[
#             Annotated[
#                 float,
#                 Field(
#                     ge=-1.0,
#                     le=1.0,
#                 ),
#             ]
#         ],
#         Field(min_length=1),
#     ]
# )


# class CorrelatedExcitatoryTsodyksMarkramSynapticModel(ExcitatoryTsodyksMarkramSynapticModel):
#     u_hill_coefficient_and_gsyn_correlation: CORRELATION_COEFFICIENT_FIELD = Field(
#         title="Correlation between U Hill Coefficient and g_syn",
#         description="Correlation coefficient between the Hill coefficient and g_syn",
#         json_schema_extra={
#             SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
#         },
#     )

#     @property
#     def cov_mat(self) -> dict:
#         return np.array(
#             [
#                 [1.0, self.u_hill_coefficient_and_gsyn_correlation],
#                 [self.u_hill_coefficient_and_gsyn_correlation, 1.0],
#             ]
#         )

#     @property
#     def cov_dict(self) -> dict:
#         return {
#             "props": ["u_hill_coefficient", "gsyn"],
#             "cov_mat": {self.source_neuron_set: {self.target_neuron_set: self.cov_mat}},
#         }
"""
