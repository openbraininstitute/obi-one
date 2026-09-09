"""The Tsodyks-Markram synaptic model: its parameters, their domains, and sampling."""

import abc
import logging
from typing import ClassVar

import numpy as np
from pandas import DataFrame
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    resolve_distribution,
)
from obi_one.scientific.blocks.synaptic_models.base import (
    SynapseModelFamily,
    SynapticModelBase,
)
from obi_one.scientific.blocks.synaptic_models.domains import (
    ParameterDomain,
    validate_parameter_samples,
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

    # Filled in by each concrete model, because the two take different values for the same
    # parameter. Keyed by the role, since that is what a config asks by and what identifies a
    # parameter across the two models; the field is what `sample` needs, and the default cannot
    # live in `json_schema_extra` because it holds a factory and would not serialize.
    _parameter_defaults: ClassVar[dict[ReferenceTag, tuple[str, DistributionDefault]]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        """Give this model's own fields the roles it plays.

        Subclasses share one `json_schema_extra` dict with the parent, so each field gets a
        fresh one rather than being mutated in place - otherwise every model would end up
        carrying whichever subclass was defined last.
        """
        super().__init_subclass__(**kwargs)
        for tag, (field_name, _default) in cls._parameter_defaults.items():
            field = cls.model_fields[field_name]
            field.json_schema_extra = {
                **(field.json_schema_extra or {}),
                SchemaKey.REFERENCE_TAG: tag,
            }

    @classmethod
    def default_distributions_by_role(cls) -> dict[str, tuple[str, Distribution]]:
        """Each parameter's fallback distribution, keyed by the role its field plays.

        A fresh distribution per call: the caller registers these into a config, which must
        not share a block with another.
        """
        return {
            tag: (default.label, default.create())
            for tag, (_field_name, default) in cls._parameter_defaults.items()
        }

    @classmethod
    def _defaults_by_field(cls) -> dict[str, DistributionDefault]:
        """The same defaults, keyed the way `sample` looks them up."""
        return dict(cls._parameter_defaults.values())

    @classmethod
    def _sampled_fields(cls) -> dict[str, tuple[str, ParameterDomain]]:
        """Each field that supplies a sampled parameter, in declaration order.

        The one place the field-to-parameter mapping is read. Declaration order is the column
        order, so `parameter_names` and `sample` cannot disagree about either.
        """
        return {
            name: (
                field.json_schema_extra[SchemaKey.SAMPLED_PARAMETER],
                ParameterDomain(**field.json_schema_extra[SchemaKey.PARAMETER_DOMAIN]),
            )
            for name, field in cls.model_fields.items()
            if isinstance(field.json_schema_extra, dict)
            and SchemaKey.SAMPLED_PARAMETER in field.json_schema_extra
        }

    @classmethod
    def parameter_names(cls) -> list[str]:
        """The columns `sample` produces, in the order it produces them."""
        return [parameter for parameter, _domain in cls._sampled_fields().values()] + [
            "syn_type_id"
        ]

    @property
    @abc.abstractmethod
    def syn_type_id(self) -> int:
        """SONATA ``syn_type_id`` assigned to these synapses (distinguishes E/I models)."""

    def sample(self, indices: DataFrame, rng: np.random.Generator | None = None) -> DataFrame:

        n = len(indices)

        def sample_from(field_name: str) -> list[float]:
            """Draw one parameter, then hold the draw to the domain its field declares."""
            parameter, domain = self._sampled_fields()[field_name]
            distribution = resolve_distribution(
                getattr(self, field_name), self._defaults_by_field()[field_name]
            )
            return validate_parameter_samples(
                parameter,
                domain,
                distribution.sample_with_constraints(n, rng=rng),
                sampled_by=type(self).__name__,
            )

        # TODO: 'shared_within' is currently ignored
        return DataFrame(
            {
                **{
                    parameter: sample_from(field_name)
                    for field_name, (parameter, _domain) in self._sampled_fields().items()
                },
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

    _parameter_defaults: ClassVar[dict[ReferenceTag, tuple[str, DistributionDefault]]] = {
        ReferenceTag.EXCITATORY_U_HILL_COEFFICIENT_DISTRIBUTION: (
            "u_hill_coefficient_distribution",
            _DEFAULT_U_HILL_COEFFICIENT,
        ),
        ReferenceTag.EXCITATORY_CONDUCTANCE_DISTRIBUTION: (
            "conductance_distribution",
            _DEFAULT_CONDUCTANCE,
        ),
        ReferenceTag.EXCITATORY_CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION: (
            "conductance_scale_factor_distribution",
            _DEFAULT_CONDUCTANCE_SCALE_FACTOR,
        ),
        ReferenceTag.EXCITATORY_FACILITATION_TIME_DISTRIBUTION: (
            "facilitation_time",
            _DEFAULT_FACILITATION_TIME,
        ),
        ReferenceTag.EXCITATORY_DEPRESSION_TIME_DISTRIBUTION: (
            "depression_time",
            _DEFAULT_DEPRESSION_TIME,
        ),
        ReferenceTag.EXCITATORY_N_RRP_VESICLES_DISTRIBUTION: (
            "n_rrp_vesicles_distribution",
            _DEFAULT_N_RRP_VESICLES,
        ),
        ReferenceTag.EXCITATORY_DECAY_TIME_DISTRIBUTION: (
            "decay_time",
            _DEFAULT_DECAY_TIME,
        ),
        ReferenceTag.EXCITATORY_U_SYN_DISTRIBUTION: (
            "u_syn",
            _DEFAULT_U_SYN,
        ),
        ReferenceTag.EXCITATORY_DELAY_DISTRIBUTION: (
            "delay_distribution",
            _DEFAULT_DELAY,
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

    _parameter_defaults: ClassVar[dict[ReferenceTag, tuple[str, DistributionDefault]]] = {
        ReferenceTag.INHIBITORY_U_HILL_COEFFICIENT_DISTRIBUTION: (
            "u_hill_coefficient_distribution",
            _DEFAULT_U_HILL_COEFFICIENT,
        ),
        ReferenceTag.INHIBITORY_CONDUCTANCE_DISTRIBUTION: (
            "conductance_distribution",
            _DEFAULT_CONDUCTANCE,
        ),
        ReferenceTag.INHIBITORY_CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION: (
            "conductance_scale_factor_distribution",
            _DEFAULT_CONDUCTANCE_SCALE_FACTOR,
        ),
        ReferenceTag.INHIBITORY_FACILITATION_TIME_DISTRIBUTION: (
            "facilitation_time",
            _DEFAULT_FACILITATION_TIME,
        ),
        ReferenceTag.INHIBITORY_DEPRESSION_TIME_DISTRIBUTION: (
            "depression_time",
            _DEFAULT_DEPRESSION_TIME,
        ),
        ReferenceTag.INHIBITORY_N_RRP_VESICLES_DISTRIBUTION: (
            "n_rrp_vesicles_distribution",
            _DEFAULT_N_RRP_VESICLES,
        ),
        ReferenceTag.INHIBITORY_DECAY_TIME_DISTRIBUTION: (
            "decay_time",
            _DEFAULT_DECAY_TIME,
        ),
        ReferenceTag.INHIBITORY_U_SYN_DISTRIBUTION: (
            "u_syn",
            _DEFAULT_U_SYN,
        ),
        ReferenceTag.INHIBITORY_DELAY_DISTRIBUTION: (
            "delay_distribution",
            _DEFAULT_DELAY,
        ),
    }

    @property
    def syn_type_id(self) -> int:
        return 7  # smaller than 100
