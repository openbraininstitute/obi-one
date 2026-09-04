"""Adapters between obi-one Task 2 configs/entities and bluepyemodel preprocessing.

Pure params compilation, morphology preflight, and the section-list catalogue live
in :mod:`bluepyemodel.preprocessing`. This module only:

- strips obi-one ``Block`` discriminators and builds BluePyEModel input schemas
- resolves IonChannelModel entities through an ``entitysdk`` client
"""

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from bluepyemodel.preprocessing.parameters import (
    NormalizedIonChannelModel,
    normalize_ion_channel_model,
)
from bluepyemodel.preprocessing.schemas import (
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


def to_bpem_parameters_selection(selection: Any) -> ParametersSelection:
    """Convert an obi-one parameter selection block to the bluepyemodel schema."""
    return ParametersSelection.model_validate(_dump_bpem_payload(selection))


def to_bpem_distributions(
    distributions: Mapping[str, Any],
) -> dict[str, DistanceDependentDistribution]:
    """Convert obi-one distance-dependent distribution declarations."""
    return {
        name: DistanceDependentDistribution.model_validate(_dump_bpem_payload(distribution))
        for name, distribution in distributions.items()
    }


def params_definition_input_from_config(config: Any) -> ParamsDefinitionInput:
    """Extract the local params-compiler inputs from an obi-one optimization config."""
    return ParamsDefinitionInput(
        parameters_selection=to_bpem_parameters_selection(config.parameters_selection),
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
        parameters_selection=to_bpem_parameters_selection(config.parameters_selection),
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
