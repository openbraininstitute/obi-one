import logging
from typing import Annotated, Never

import bluepysnap as snap
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_parameterization.base import SynapseParameterization
from obi_one.scientific.unions.unions_distributions import (
    SynapticParameterizationDistributionReference,
)
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference

L = logging.getLogger(__name__)


class TsodyksMarkramSynapseParameterization(SynapseParameterization):
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: True,
        },
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: False,
        },
    )

    u_hill_coefficient_distribution: SynapticParameterizationDistributionReference = Field(
        title="U Hill Coefficient Distribution",
        description="Distribution of the Hill coefficient for the steady-state utilization"
        " of synaptic efficacy (u).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: SynapticParameterizationDistributionReference.__name__,
        },
    )

    def go_for_it(self, circ: snap.Circuit) -> Never:
        msg = "New synapse parameterization not implemented yet!"
        raise NotImplementedError(msg)


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


class CorrelatedTsodyksMarkramSynapseParameterization(TsodyksMarkramSynapseParameterization):
    u_hill_coefficient_and_b_correlation: CORRELATION_COEFFICIENT_FIELD = Field(
        title="Correlation between U Hill Coefficient and b",
        description="Correlation coefficient between the Hill coefficient and X",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
