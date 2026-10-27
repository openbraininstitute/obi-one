"""Adapters between obi-one Task 2 configs/entities and bluepyemodel preprocessing.

Pure params compilation, morphology preflight, and the section-list catalogue live
in :mod:`bluepyemodel.preprocessing`. This module only:

- strips obi-one ``Block`` discriminators and builds BluePyEModel input schemas
- resolves IonChannelModel entities through an ``entitysdk`` client
"""

from collections.abc import Iterable, Mapping
from itertools import starmap
from typing import TYPE_CHECKING, Any

from bluepyemodel.preprocessing.parameters import (
    NormalizedIonChannelModel,
    normalize_ion_channel_model,
)
from bluepyemodel.preprocessing.schemas import (
    STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS,
    CustomDistanceDependentDistribution as BpemCustomDistanceDependentDistribution,
    DistanceDependentDistribution,
    OptimizationArtifactInput,
    ParametersSelection,
    ParamsDefinitionInput,
)

if TYPE_CHECKING:
    from bluepyemodel.preprocessing.morphology_preflight import MorphologyCapabilities

    from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID

# Every obi-one ``Block`` carries a ``type`` discriminator that no preprocessing
# schema declares, and those schemas forbid extra fields.
_BLOCK_DISCRIMINATOR = "type"


def _strip_block_metadata(value: Any) -> Any:
    """Drop ``Block`` discriminators from a ``model_dump(mode='python')`` tree."""
    if isinstance(value, Mapping):
        return {
            key: _strip_block_metadata(nested)
            for key, nested in value.items()
            if key != _BLOCK_DISCRIMINATOR
        }
    if isinstance(value, (list, tuple)):
        return [_strip_block_metadata(item) for item in value]
    return value


def _dump_bpem_payload(block: Any) -> Any:
    """Serialize an obi-one block into a bluepyemodel-compatible payload."""
    return _strip_block_metadata(block.model_dump(mode="python"))


def to_bpem_parameters_selection(
    selection: Any,
    distributions: Mapping[str, Any],
) -> ParametersSelection:
    """Convert an obi-one parameter selection block to the bluepyemodel schema.

    Parameters reference a distribution by its ``distance_dependent_distributions`` key. Those
    references are translated to the name the compiler looks up via :func:`bpem_distribution_name`:
    identical to the key for every distribution except runtime-name standards (``step``), which
    use their canonical name.
    """
    resolver_names = {
        key: bpem_distribution_name(key, distribution)
        for key, distribution in distributions.items()
        if bpem_distribution_name(key, distribution) != key
    }
    payload = _dump_bpem_payload(selection)
    if resolver_names:
        for field_name in ("base_parameters", "mechanism_regions"):
            _retarget_distribution_references(payload.get(field_name), resolver_names)
    return ParametersSelection.model_validate(payload)


def _retarget_distribution_references(value: Any, resolver_names: Mapping[str, str]) -> None:
    """Rewrite ``distribution`` references in a dumped selection subtree in place.

    Only keys present in ``resolver_names`` are rewritten; every other reference already matches
    the name the compiler uses and is left unchanged.
    """
    if isinstance(value, Mapping):
        reference = value.get("distribution")
        if isinstance(reference, str) and reference in resolver_names:
            value["distribution"] = resolver_names[reference]
        for nested in value.values():
            _retarget_distribution_references(nested, resolver_names)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _retarget_distribution_references(item, resolver_names)


def bpem_distribution_name(key: str, distribution: Any) -> str:
    """Name parameters use to reference a declared distribution.

    The dictionary key is the distribution's identity, except for distributions BluePyEModel
    resolves by their canonical name at runtime (``requires_runtime_name``, currently ``step``),
    which use their class-intrinsic ``default_name`` whatever key the user gave them.
    """
    if distribution.requires_runtime_name:
        return type(distribution).default_name
    return key


def to_bpem_distributions(
    distributions: Mapping[str, Any],
) -> dict[str, DistanceDependentDistribution]:
    """Convert the distribution declarations for the BluePyEModel params compiler.

    Results are keyed by :func:`bpem_distribution_name`. Runtime-name distributions (``step``)
    use their canonical name and are validated as their BluePyEModel class so the runtime
    placeholders stay valid. Every other distribution (custom formulas and self-contained
    standards such as ``exp``) keeps its dictionary key and is validated as the generic schema,
    carrying its own function.

    Raises:
        ValueError: If two declarations resolve to the same distribution name.
    """
    names = list(starmap(bpem_distribution_name, distributions.items()))
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        msg = f"Distance-dependent distributions declared more than once: {duplicates}."
        raise ValueError(msg)
    converted: dict[str, DistanceDependentDistribution] = {}
    for name, distribution in zip(names, distributions.values(), strict=True):
        schema = (
            type(STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS[name])
            if distribution.requires_runtime_name
            else DistanceDependentDistribution
        )
        converted[name] = schema.model_validate(distribution.to_bpem_payload())
    return converted


def to_bpem_custom_distributions(
    distributions: Mapping[str, Any],
) -> dict[str, BpemCustomDistanceDependentDistribution]:
    """Convert the resolver-visible entries of a distribution dictionary to bluepyemodel schemas.

    Keyed by :func:`bpem_distribution_name`. Runtime-name distributions (``step``) are skipped:
    BluePyEModel resolves them from its built-in catalogue by canonical name. Every other
    distribution (custom formulas and self-contained standards such as ``exp``) is exposed here
    under its dictionary key, so the resolver finds it by the same name the parameters reference.
    """
    return {
        bpem_distribution_name(key, distribution): (
            BpemCustomDistanceDependentDistribution.model_validate(distribution.to_bpem_payload())
        )
        for key, distribution in distributions.items()
        if not distribution.requires_runtime_name
    }


def params_definition_input_from_config(config: Any) -> ParamsDefinitionInput:
    """Extract the local params-compiler inputs from an obi-one optimization config."""
    return ParamsDefinitionInput(
        parameters_selection=to_bpem_parameters_selection(
            config.parameters_selection,
            config.distance_dependent_distributions,
        ),
        distance_dependent_distributions=to_bpem_distributions(
            config.distance_dependent_distributions,
        ),
    )


def optimization_artifact_input_from_config(
    config: Any,
    *,
    mtype: str | None,
    morphology_filename: str,
    morphology_capabilities: "MorphologyCapabilities | None" = None,
) -> OptimizationArtifactInput:
    """Extract the local artifact-compiler inputs from an obi-one optimization config."""
    return OptimizationArtifactInput(
        config_contract_version=config.contract_version,
        emodel=config.initialize.emodel,
        parameters_selection=to_bpem_parameters_selection(
            config.parameters_selection,
            config.distance_dependent_distributions,
        ),
        distance_dependent_distributions=to_bpem_distributions(
            config.distance_dependent_distributions,
        ),
        pipeline_settings_overrides={
            **config.morphology_settings.to_pipeline_settings(),
            **config.optimization_settings.to_dict(config.optimization_params),
        },
        mtype=mtype,
        morphology_filename=morphology_filename,
        morphology_capabilities=morphology_capabilities,
    )


def resolve_ion_channel_models(
    references: Iterable["IonChannelModelFromID"],
    db_client: Any,
) -> dict[str, NormalizedIonChannelModel]:
    """Resolve selected IonChannelModel references and normalize their metadata."""
    normalized: dict[str, NormalizedIonChannelModel] = {}
    for reference in references:
        normalized[reference.id_str] = normalize_ion_channel_model(
            reference.entity(db_client=db_client),
            entity_id=reference.id_str,
        )
    return normalized


def fetch_variable_catalog(
    ion_channel_ids: Iterable[str],
    db_client: Any,
) -> dict[str, NormalizedIonChannelModel]:
    """Fetch and normalize the RANGE/GLOBAL/conductance variable catalog for entities.

    UI clients must consume this catalog through the ``GET /declared/mapped-ion-channel-
    properties/emodel-optimization-variables`` endpoint rather than re-deriving qualified
    names from raw EntitySDK ``neuron_block`` data, so the ``gNa`` → ``gNa_NaTg`` naming
    rule cannot drift between the compiler and the form.

    Returns a mapping keyed by entity ID, matching the shape used internally by
    :func:`resolve_ion_channel_models`.
    """
    from entitysdk.models import IonChannelModel  # ruff: ignore[import-outside-top-level]

    catalog: dict[str, NormalizedIonChannelModel] = {}
    for ion_channel_id in ion_channel_ids:
        entity = db_client.get_entity(
            entity_id=ion_channel_id,
            entity_type=IonChannelModel,
        )
        catalog[str(ion_channel_id)] = normalize_ion_channel_model(
            entity,
            entity_id=str(ion_channel_id),
        )
    return catalog
