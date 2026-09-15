"""Working-directory staging for the BluePyEModel optimisation stage.

Downloads entity assets, resolves morphology metadata, and builds the versioned
params/recipe artifact bundle into a coordinate output root.
"""

import logging
from pathlib import Path

import entitysdk
from bluepyemodel.preprocessing import (
    MorphologyCapabilities,
    NormalizedIonChannelModel,
    OptimizationArtifacts,
    build_optimization_artifacts,
)

from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    optimization_artifact_input_from_config,
    resolve_ion_channel_models,
)

L = logging.getLogger(__name__)


def download_extraction_features(
    config: EModelOptimizationSingleConfig,
    extraction_tr: TaskResultFromID,
    coord_root: Path,
    db_client: entitysdk.client.Client,
) -> Path:
    """Download extracted features JSON from extraction TaskResult."""
    from entitysdk.types import AssetLabel  # ruff: ignore[import-outside-top-level]

    features_dir = coord_root / "config" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    path = extraction_tr.download_asset_by_label(
        AssetLabel.efeature_extraction_features,
        dest_dir=features_dir,
        db_client=db_client,
    )
    # Rename to <emodel>.json if needed
    target = features_dir / f"{config.initialize.emodel}.json"
    if path != target:
        path.rename(target)
    L.info("Staged extracted features: %s", target)
    return target


def stage_morphology(
    config: EModelOptimizationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.client.Client,
) -> str:
    """Download morphology SWC and return the filename."""
    morph_dir = coord_root / "morphologies"
    morph_dir.mkdir(parents=True, exist_ok=True)
    morph_entity = config.inputs.morphology
    swc_content = morph_entity.swc_file_content(db_client=db_client)
    # Use entity ID as filename base
    morph_id = morph_entity.id_str
    morph_filename = f"{morph_id}.swc"
    (morph_dir / morph_filename).write_text(
        swc_content,
        encoding="utf-8",
    )
    L.info("Staged morphology: %s", morph_filename)
    return morph_filename


def stage_mechanisms(
    config: EModelOptimizationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.client.Client,
) -> None:
    """Download .mod files from all referenced ion channel model entities."""
    mech_dir = coord_root / "mechanisms"
    mech_dir.mkdir(parents=True, exist_ok=True)
    references = config.parameters_selection.ion_channel_model_references
    for reference in references:
        reference.download_asset(dest_dir=mech_dir, db_client=db_client)
    L.info("Staged %d ion channel models.", len(references))


def build_artifacts(
    config: EModelOptimizationSingleConfig,
    *,
    db_client: entitysdk.client.Client,
    mtype: str | None,
    morph_filename: str,
    morphology_capabilities: MorphologyCapabilities,
    normalized_models: dict[str, NormalizedIonChannelModel] | None = None,
) -> OptimizationArtifacts:
    """Build artifacts from EntityCore metadata resolved by entity IDs."""
    if normalized_models is None:
        references = config.parameters_selection.ion_channel_model_references
        normalized_models = resolve_ion_channel_models(references, db_client)
    return build_optimization_artifacts(
        optimization_artifact_input_from_config(
            config,
            mtype=mtype,
            morphology_filename=morph_filename,
            morphology_capabilities=morphology_capabilities,
        ),
        normalized_models,
    )


def stage_traces(
    extraction_tr: TaskResultFromID,
    db_client: entitysdk.client.Client,
) -> list[str]:
    """Fetch trace IDs via derivation chain from extraction TaskResult.

    Returns a list of trace (ElectricalCellRecording) IDs. The actual NWB
    assets are not downloaded because the optimisation stage only needs
    the extracted features and protocols, not the raw traces.
    """
    from entitysdk.models import Derivation  # ruff: ignore[import-outside-top-level]

    tr_entity = extraction_tr.entity(db_client=db_client)
    derivations = db_client.search_entity(
        entity_type=Derivation,
        query={"generated__id": tr_entity.id},
    )

    trace_ids: list[str] = [
        str(deriv.used.id) for deriv in derivations if deriv.used and deriv.used.id
    ]
    L.info("Found %d trace IDs via derivation chain (assets not downloaded).", len(trace_ids))
    return trace_ids


def derive_mtype(
    config: EModelOptimizationSingleConfig,
    db_client: entitysdk.client.Client,
) -> str | None:
    """Derive mtype from the selected morphology entity.

    Uses the first m-type if multiple are available. Returns None when
    the morphology has no m-types, which is acceptable for optimisation.
    """
    morph_entity = config.inputs.morphology
    entity = morph_entity.entity(db_client=db_client)
    if hasattr(entity, "mtypes") and entity.mtypes:
        return str(entity.mtypes[0].pref_label)  # ty:ignore[not-subscriptable]
    return None
