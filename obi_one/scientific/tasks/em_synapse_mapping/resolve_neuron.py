"""Shared neuron resolution logic for single- and multi-neuron synapse mapping tasks.

Resolves a neuron reference (CellMorphologyFromID or MEModelFromID) into:
- morphology entity and files (H5 for spiny, SWC for all)
- provenance (pt_root_id, source mesh, source dataset)
- ME model properties (if applicable)
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy  # NOQA: ICN001
from entitysdk import Client
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import EMCellMesh, EMDenseReconstructionDataset
from morph_spines import MorphologyWithSpines, load_morphology_with_spines

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

L = logging.getLogger(__name__)


@dataclass
class ResolvedNeuron:
    """Result of resolving a neuron reference."""

    pt_root_id: int
    morph_entity: object
    morph_from_id: CellMorphologyFromID
    spiny_morph: MorphologyWithSpines | None
    smooth_morph: object  # neurom.core.Morphology
    source_mesh_entity: EMCellMesh
    source_dataset: EMDenseReconstructionDataset
    cave_version: int
    use_me_model: bool
    phys_node_props: dict = field(default_factory=dict)
    fn_morph_h5: Path | None = None
    fn_morph_swc: Path | None = None


def resolve_provenance(
    db_client: Client, morph_from_id: CellMorphologyFromID
) -> tuple[int, EMCellMesh, EMDenseReconstructionDataset]:
    source_mesh_entity = morph_from_id.source_mesh_entity(db_client=db_client)
    pt_root_id = source_mesh_entity.dense_reconstruction_cell_id
    source_dataset = db_client.get_entity(
        entity_id=source_mesh_entity.em_dense_reconstruction_dataset.id,
        entity_type=EMDenseReconstructionDataset,
    )
    return pt_root_id, source_mesh_entity, source_dataset


def resolve_neuron(
    neuron_ref: CellMorphologyFromID | MEModelFromID,
    db_client: Client,
    out_root: Path,
) -> ResolvedNeuron:
    """Resolve a neuron reference into morphology files, provenance, and ME model properties.

    Args:
        neuron_ref: A CellMorphologyFromID or MEModelFromID reference.
        db_client: Entity SDK client.
        out_root: Root output directory for morphology files.

    Returns:
        A ResolvedNeuron with all resolved information.
    """
    use_me_model = isinstance(neuron_ref, MEModelFromID)
    if use_me_model:
        me_model_entity = neuron_ref.entity(db_client)
        morph_entity = me_model_entity.morphology
        morph_from_id = CellMorphologyFromID(id_str=str(morph_entity.id))
    else:
        morph_entity = neuron_ref.entity(db_client)
        morph_from_id = neuron_ref

    # Place and load morphologies
    L.info("Placing morphologies...")
    fn_morphology_out_h5 = Path("morphologies") / (morph_entity.name + ".h5")
    fn_morphology_out_swc = Path("morphologies/morphology") / (morph_entity.name + ".swc")
    morph_from_id.write_spiny_neuron_h5(out_root / fn_morphology_out_h5, db_client=db_client)
    smooth_morph = morph_from_id.neurom_morphology(db_client)
    smooth_morph.to_morphio().as_mutable().write(out_root / fn_morphology_out_swc)
    spiny_morph = load_morphology_with_spines(str(out_root / fn_morphology_out_h5))

    phys_node_props = {}
    if use_me_model:
        L.info("Placing mechanisms and .hoc file...")
        tmp_staging = out_root / f"temp_staging_{morph_entity.name}"
        memdl_paths = download_memodel(db_client, me_model_entity, tmp_staging)
        shutil.move(memdl_paths.mechanisms_dir, out_root / "mechanisms")
        hoc_dir = out_root / "hoc"
        hoc_dir.mkdir(parents=True)
        shutil.move(memdl_paths.hoc_path, hoc_dir)
        shutil.rmtree(tmp_staging)
        phys_node_props["model_template"] = numpy.array([f"hoc:{memdl_paths.hoc_path.stem}"])
        phys_node_props["model_type"] = numpy.array([0], dtype=numpy.int32)
        phys_node_props["morph_class"] = numpy.array([0], dtype=numpy.int32)
        if me_model_entity.calibration_result is not None:
            phys_node_props["threshold_current"] = numpy.array(
                [me_model_entity.calibration_result.threshold_current], dtype=numpy.float32
            )
            phys_node_props["holding_current"] = numpy.array(
                [me_model_entity.calibration_result.holding_current], dtype=numpy.float32
            )

    L.info("Resolving skeleton provenance...")
    pt_root_id, source_mesh_entity, source_dataset = resolve_provenance(db_client, morph_from_id)

    return ResolvedNeuron(
        pt_root_id=pt_root_id,
        morph_entity=morph_entity,
        morph_from_id=morph_from_id,
        spiny_morph=spiny_morph,
        smooth_morph=smooth_morph,
        source_mesh_entity=source_mesh_entity,
        source_dataset=source_dataset,
        cave_version=source_mesh_entity.release_version,
        use_me_model=use_me_model,
        phys_node_props=phys_node_props,
        fn_morph_h5=fn_morphology_out_h5,
        fn_morph_swc=fn_morphology_out_swc,
    )
