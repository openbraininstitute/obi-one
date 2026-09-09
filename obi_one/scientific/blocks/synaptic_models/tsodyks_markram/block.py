"""The Tsodyks-Markram synaptic model: its parameters, their domains, and sampling."""

import abc
import logging
from typing import ClassVar

import numpy as np
from pandas import DataFrame
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    resolve_distribution,
)
from obi_one.scientific.blocks.synaptic_models.base import (
    SynapseModelFamily,
    SynapticModelBase,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.distributions import (
    _DEFAULT_CONDUCTANCE,
    _DEFAULT_CONDUCTANCE_SCALE_FACTOR,
    _DEFAULT_DECAY_TIME,
    _DEFAULT_DELAY,
    _DEFAULT_DEPRESSION_TIME,
    _DEFAULT_FACILITATION_TIME,
    _DEFAULT_N_RRP_VESICLES,
    _DEFAULT_U_HILL_COEFFICIENT,
    _DEFAULT_U_SYN,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.domains import (
    ParameterDomain,
    validate_parameter_samples,
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
            "efficacy (u). Defaults to "
            f"{_DEFAULT_U_HILL_COEFFICIENT.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_U_HILL_COEFFICIENT.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.U_HILL_COEFFICIENT_DISTRIBUTION,
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive finite value"
            )._asdict(),
        },
    )

    conductance_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Conductance (g_syn) Distribution",
        description=(
            "Distribution of synaptic conductance (g_syn). Defaults to "
            f"{_DEFAULT_CONDUCTANCE.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_CONDUCTANCE.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.CONDUCTANCE_DISTRIBUTION,
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
            "outside of the range of the conductance distribution. Defaults to "
            f"{_DEFAULT_CONDUCTANCE_SCALE_FACTOR.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_CONDUCTANCE_SCALE_FACTOR.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION,
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive finite value"
            )._asdict(),
        },
    )

    facilitation_time: AllDistributionsReference | None = Field(
        default=None,
        title="Facilitation Time Distribution",
        description=(
            "Distribution of facilitation time in milliseconds. Defaults to "
            f"{_DEFAULT_FACILITATION_TIME.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_FACILITATION_TIME.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.FACILITATION_TIME_DISTRIBUTION,
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive time in milliseconds"
            )._asdict(),
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    depression_time: AllDistributionsReference | None = Field(
        default=None,
        title="Depression Time Distribution",
        description=(
            "Distribution of depression time in milliseconds. Defaults to "
            f"{_DEFAULT_DEPRESSION_TIME.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_DEPRESSION_TIME.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.DEPRESSION_TIME_DISTRIBUTION,
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=0.0, minimum_inclusive=False, description="a positive time in milliseconds"
            )._asdict(),
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    n_rrp_vesicles_distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Number of RRP Vesicles Distribution",
        description=(
            "Distribution of the number of readily releasable pool (RRP) vesicles. Defaults to "
            f"{_DEFAULT_N_RRP_VESICLES.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_N_RRP_VESICLES.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.N_RRP_VESICLES_DISTRIBUTION,
            SchemaKey.PARAMETER_DOMAIN: ParameterDomain(
                minimum=1.0, integer=True, description="an integer value greater than or equal to 1"
            )._asdict(),
        },
    )

    decay_time: AllDistributionsReference | None = Field(
        default=None,
        title="Decay Time Distribution",
        description=(
            "Distribution of decay time in milliseconds. Defaults to "
            f"{_DEFAULT_DECAY_TIME.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_DECAY_TIME.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.DECAY_TIME_DISTRIBUTION,
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
            "in a spike train. Defaults to "
            f"{_DEFAULT_U_SYN.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_U_SYN.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.U_SYN_DISTRIBUTION,
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
            "Defaults to "
            f"{_DEFAULT_DELAY.description}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.DEFAULT_BLOCK_REFERENCE_LABEL: _DEFAULT_DELAY.label,
            SchemaKey.REFERENCE_TAG: ReferenceTag.DELAY_DISTRIBUTION,
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
            default: DistributionDefault,
            field_name: str | None = None,
        ) -> list[float]:
            """Draw a parameter, then hold the draw to the domain its field declares.

            `field_name` only when it differs from the parameter it supplies, which it does
            for the five fields whose names carry a `_distribution` suffix.
            """
            field_name = field_name or parameter_name
            extra = type(self).model_fields[field_name].json_schema_extra
            domain = ParameterDomain(**extra[SchemaKey.PARAMETER_DOMAIN])
            samples = resolve_distribution(
                getattr(self, field_name), default
            ).sample_with_constraints(n, rng=rng)
            return validate_parameter_samples(parameter_name, domain, samples)

        # TODO: 'shared_within' is currently ignored
        return DataFrame(
            {
                "u_hill_coefficient": sample_from(
                    "u_hill_coefficient",
                    _DEFAULT_U_HILL_COEFFICIENT,
                    field_name="u_hill_coefficient_distribution",
                ),
                "conductance": sample_from(
                    "conductance",
                    _DEFAULT_CONDUCTANCE,
                    field_name="conductance_distribution",
                ),
                "conductance_scale_factor": sample_from(
                    "conductance_scale_factor",
                    _DEFAULT_CONDUCTANCE_SCALE_FACTOR,
                    field_name="conductance_scale_factor_distribution",
                ),
                "facilitation_time": sample_from(
                    "facilitation_time",
                    _DEFAULT_FACILITATION_TIME,
                ),
                "depression_time": sample_from(
                    "depression_time",
                    _DEFAULT_DEPRESSION_TIME,
                ),
                "n_rrp_vesicles": sample_from(
                    "n_rrp_vesicles",
                    _DEFAULT_N_RRP_VESICLES,
                    field_name="n_rrp_vesicles_distribution",
                ),
                "decay_time": sample_from(
                    "decay_time",
                    _DEFAULT_DECAY_TIME,
                ),
                "u_syn": sample_from(
                    "u_syn",
                    _DEFAULT_U_SYN,
                ),
                "delay": sample_from(
                    "delay",
                    _DEFAULT_DELAY,
                    field_name="delay_distribution",
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
