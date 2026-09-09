from enum import StrEnum
from typing import ClassVar

import numpy as np
from pandas import DataFrame

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks import distributions
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    resolve_distribution,
)
from obi_one.scientific.blocks.synaptic_models.domains import (
    ParameterDomain,
    validate_parameter_samples,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag


class SynapseModelFamily(StrEnum):
    """Families of synapse model, one per set of synapse parameters.

    Membership of a family is what makes two synaptic models interchangeable: they
    provide the same parameters, so one can stand in for the other. A closed set of
    them rather than free strings, so that a typo cannot invent a family nobody is
    compatible with, and so the families that need a default can be enumerated.
    """

    TSODYKS_MARKRAM = "TsodyksMarkram"


class SynapticModelBase(Block):
    # ClassVar, not a bare annotation: pydantic turns an annotated underscore attribute into
    # a ModelPrivateAttr, and `cls._synapse_model_family` then yields that wrapper rather
    # than the member, so both the None check below and every family comparison read it wrong.
    _synapse_model_family: ClassVar[SynapseModelFamily | None] = None

    @classmethod
    def synapse_model_family(cls) -> SynapseModelFamily:
        if cls._synapse_model_family is None:
            msg = (
                "Concrete subclasses of SynapticModelBase MUST set the class variable "
                "_synapse_model_family to the SynapseModelFamily member they belong to. "
                "This is used to check compatibility of different SynapticModelBase subclasses."
            )
            raise NotImplementedError(msg)
        return cls._synapse_model_family

    @classmethod
    def from_dict(
        cls, serialized_dict: dict
    ) -> tuple["SynapticModelBase", dict[str, Distribution]]:

        def dist_ref(name: str) -> AllDistributionsReference:
            """Helper to create a distribution reference."""
            return AllDistributionsReference(block_dict_name="distributions", block_name=name)

        if serialized_dict["class"] != cls.__name__:
            msg = (
                f"Expected class name {cls.__name__!r} in serialized dict",
                f"got {serialized_dict['class']!r}",
            )
            raise ValueError(msg)
        distr_obj_dict = {}
        distr_ref_dict = {}
        for param_name, distr_dict in serialized_dict["distributions"].items():
            distr_cls = distr_dict.pop("type")
            distr_obj_dict[param_name] = distributions.__dict__[distr_cls](**distr_dict)
            distr_ref_dict[param_name] = dist_ref(param_name)
            distr_ref_dict[param_name].block = distr_obj_dict[param_name]
        return cls(**distr_ref_dict), distr_obj_dict

    # Filled in by each concrete model. Keyed by the role, since that is what a config asks
    # by and what identifies a parameter across models that declare the same field; the field
    # is what `sample` needs, and the default cannot live in `json_schema_extra` because it
    # holds a factory and would not serialize.
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
    def syn_type_id(self) -> int:
        """SONATA ``syn_type_id`` assigned to these synapses (distinguishes E/I models)."""
        msg = (
            "Concrete subclasses of SynapticModelBase MUST provide a .syn_type_id, the SONATA "
            "value written for every synapse they parameterize."
        )
        raise NotImplementedError(msg)

    def sample(self, indices: DataFrame, rng: np.random.Generator | None = None) -> DataFrame:
        """Draw every parameter this model declares, one column each.

        The input is a DataFrame with `@source_node` and `@target_node` columns, indexed by
        SONATA edge index; the output carries the same index.

        `rng` is the source of randomness for every parameter drawn, so that one generator is
        shared across them: each distribution otherwise seeds itself from its own `random_seed`,
        and two parameters given the same distribution then draw the same values for every
        synapse. Callers that leave it unset keep that per-distribution behaviour.
        """
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
