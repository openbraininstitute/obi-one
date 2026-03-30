import logging
from typing import Annotated

import numpy as np
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
)

L = logging.getLogger(__name__)


class TsodyksMarkramSynapticModel(Block):
    u_hill_coefficient_distribution: AllDistributionsReference = Field(
        title="U Hill Coefficient Distribution",
        description="Distribution of the Hill coefficient for the steady-state utilization"
        " of synaptic efficacy (u).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    conductance_distribution: AllDistributionsReference = Field(
        title="Conductance (g_syn) Distribution",
        description="Distribution of synaptic conductance (g_syn).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    conductance_scale_factor_distribution: AllDistributionsReference = Field(
        title="Conductance Scale Factor Distribution",
        description="Distribution of the conductance scale factor that multiplies the synaptic "
        "conductance (g_syn) to allow for fitting of synaptic conductance values that are "
        "outside of the range of the conductance distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    fascilitation_time: AllDistributionsReference = Field(
        title="Fascilitation Time Distribution",
        description="Fascilitation Time Distribution",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    depression_time: AllDistributionsReference = Field(
        title="Depression Time Distribution",
        description="Depression Time Distribution",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    n_rrp_vesicles_distribution: AllDistributionsReference = Field(
        title="Number of RRP Vesicles Distribution",
        description="Distribution of the number of readily releasable pool (RRP) vesicles.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    decay_time: AllDistributionsReference = Field(
        title="Decay Time Distribution",
        description="Decay Time Distribution",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    usyn: AllDistributionsReference = Field(
        title="Usyn Distribution",
        description="Distribution of the utilization of synaptic efficacy (usyn) for "
        "the first spike in a spike train.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
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

    @property
    def cov_mat(self) -> dict:
        return []

    @property
    def cov_dict(self) -> dict:
        return {}

    @property
    def synapse_type_id(self) -> int:
        return 113  # 128, 130, 114, 123 are other values in edges files

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

    def parameter_dictionaries(self) -> dict:
        return {
            "u_hill_coefficient": self.u_hill_coefficient_dict(),
            "conductance": self.conductance_distribution_dict(),
            "conductance_scale_factor": self.conductance_scale_factor_distribution_dict(),
            "fascilitation_time": self.fascilitation_time_dict(),
            "depression_time": self.depression_time_dict(),
            "n_rrp_vesicles": self.n_rrp_vesicles_dict(),
            "decay_time": self.decay_time_dict(),
            "usyn": self.usyn_dict(),
            "synapse_type_id": self.synapse_type_id,
        }


CORRELATION_COEFFICIENT_FIELD = (
    Annotated[
        float,
        Field(ge=-1.0, le=1.0),
    ]
    | Annotated[
        list[
            Annotated[
                float,
                Field(
                    ge=-1.0,
                    le=1.0,
                ),
            ]
        ],
        Field(min_length=1),
    ]
)


class CorrelatedTsodyksMarkramSynapticModel(TsodyksMarkramSynapticModel):
    u_hill_coefficient_and_gsyn_correlation: CORRELATION_COEFFICIENT_FIELD = Field(
        title="Correlation between U Hill Coefficient and g_syn",
        description="Correlation coefficient between the Hill coefficient and g_syn",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    @property
    def cov_mat(self) -> dict:
        return np.array(
            [
                [1.0, self.u_hill_coefficient_and_gsyn_correlation],
                [self.u_hill_coefficient_and_gsyn_correlation, 1.0],
            ]
        )

    @property
    def cov_dict(self) -> dict:
        return {
            "props": ["u_hill_coefficient", "gsyn"],
            "cov_mat": {self.source_neuron_set: {self.target_neuron_set: self.cov_mat}},
        }
