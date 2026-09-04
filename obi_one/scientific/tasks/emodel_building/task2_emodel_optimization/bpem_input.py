"""Adapt obi-one Task 2 config objects into bluepyemodel preprocessing schemas."""

from collections.abc import Mapping
from typing import Any

from bluepyemodel.preprocessing.morphology_preflight import MorphologyCapabilities
from bluepyemodel.preprocessing.schemas import (
    DistanceDependentDistribution,
    OptimizationArtifactInput,
    ParametersSelection,
    ParamsDefinitionInput,
)

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
    morphology_capabilities: MorphologyCapabilities | None = None,
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
