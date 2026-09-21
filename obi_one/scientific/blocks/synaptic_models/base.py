from enum import StrEnum
from typing import ClassVar

import numpy as np
from pandas import DataFrame

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.defaults import (
    DistributionDefault,
    resolve_distribution,
)
from obi_one.scientific.blocks.synaptic_models.domains import (
    ParameterDomain,
    clip_parameter_samples,
)
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

    # ClassVar, not a bare annotation, for the same reason as `_synapse_model_family` above.
    # The SONATA edge population `type` string(s) (e.g. "chemical") this model's parameters
    # are meaningful for. Different population types carry entirely different parameter sets
    # (a Tsodyks-Markram model's parameters have no counterpart on an "Exp2Syn_synapse" or
    # "point_process" population), so this cannot be inferred from `synapse_model_family` or
    # from any coarser chemical/electrical split - it has to be declared per model.
    _compatible_edge_population_types: ClassVar[tuple[str, ...] | None] = None

    @classmethod
    def compatible_edge_population_types(cls) -> tuple[str, ...]:
        """SONATA edge population ``type`` string(s) this model can be assigned to.

        Checked by ``SynapseModelAssigner.validate_for_circuit`` before any synapse is
        written, so that assigning e.g. a Tsodyks-Markram model to an ``"Exp2Syn_synapse"``
        or electrical population is rejected instead of writing columns the mechanism the
        edge population actually uses does not read.
        """
        if cls._compatible_edge_population_types is None:
            msg = (
                "Concrete subclasses of SynapticModelBase MUST set the class variable "
                "_compatible_edge_population_types to the SONATA edge population type(s) "
                "(e.g. ('chemical',)) this model's parameters apply to."
            )
            raise NotImplementedError(msg)
        return cls._compatible_edge_population_types

    # Filled in by each concrete model. Keyed by the tag, since that is what a config answers
    # by and what identifies a parameter across models that declare the same field; the field
    # is what `sample` needs, and the default cannot live in `json_schema_extra` because it
    # holds a factory and would not serialize.
    _parameter_defaults: ClassVar[dict[ReferenceTag, tuple[str, DistributionDefault]]] = {}

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs) -> None:  # ruff: ignore[bad-dunder-method-name]
        """Stamp each field this model declares a default for with the tag that names it.

        The parameter fields are declared once, on a shared parent, but two models can need
        different tags for the same field - excitatory and inhibitory facilitation time are
        different things with different defaults. So the tag cannot be written into the
        declaration; it has to be applied per subclass, once the subclass exists.

        Three details make that work, and none of them is optional:

        - `__pydantic_init_subclass__`, not `__init_subclass__`. Pydantic has not built the
          subclass's `model_fields` when the latter runs, so `cls.model_fields` is still the
          *parent's* and the stamp lands on the parent's own field objects, leaving it
          carrying whichever subclass was defined last.
        - a fresh `json_schema_extra` rather than a mutated one. Subclasses get their own
          `FieldInfo` but it holds the *same* extra dict by reference, so writing into it in
          place gives every sibling whichever subclass was defined last.
        - `model_rebuild`, because this hook runs *after* the JSON schema has been built. The
          UI reads the tag out of the published schema, so a stamp that never reaches it is
          the same as no stamp at all - the fields go back to sharing one type-keyed label.
        """
        super().__pydantic_init_subclass__(**kwargs)
        if not cls._parameter_defaults:
            return
        for tag, (field_name, _default) in cls._parameter_defaults.items():
            field = cls.model_fields[field_name]
            field.json_schema_extra = {
                **(field.json_schema_extra or {}),
                SchemaKey.REFERENCE_TAG: tag,
            }
        cls.model_rebuild(force=True)

    @classmethod
    def default_distributions_by_tag(cls) -> dict[ReferenceTag, tuple[str, Distribution]]:
        """Each parameter's fallback distribution, keyed by the tag naming its field.

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

    def _reject_unimplemented_shared_within(self) -> None:
        """Fail loudly if any ``*_shared_within`` flag is set.

        Per-connection sharing is declared on the model but not yet implemented in `sample`
        (the fields are hidden in the UI so it cannot be reached from there). Guard the one
        code path that would otherwise honour them, so a config that sets one programmatically
        fails rather than silently drawing every value independently. Discovered by name so a
        future field is covered without touching this check.
        """
        enabled = [
            name
            for name in type(self).model_fields
            if name.endswith("_shared_within") and getattr(self, name)
        ]
        if enabled:
            msg = (
                "'shared_within' (per-connection parameter sharing) is not implemented yet; "
                f"cannot honour {enabled}. Leave these unset until it is supported."
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
        self._reject_unimplemented_shared_within()

        n = len(indices)
        defaults = self._defaults_by_field()

        columns: dict[str, list] = {}
        for field_name, (parameter, domain) in self._sampled_fields().items():
            distribution = resolve_distribution(getattr(self, field_name), defaults[field_name])
            columns[parameter] = clip_parameter_samples(
                parameter,
                domain,
                distribution.sample_with_constraints(n, rng=rng),
                sampled_by=type(self).__name__,
            )
        columns["syn_type_id"] = [self.syn_type_id] * n
        return DataFrame(columns, index=indices.index)
