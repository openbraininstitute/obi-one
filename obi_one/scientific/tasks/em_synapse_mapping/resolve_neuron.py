"""Shared neuron resolution logic for single- and multi-neuron synapse mapping tasks.

Resolves a neuron reference (CellMorphologyFromID or MEModelFromID) into:
- morphology entity and files (H5 for spiny, SWC for all)
- provenance (pt_root_id, source mesh, source dataset)
- ME model properties (if applicable)
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy  # ruff: ignore[unconventional-import-alias]
import pandas  # ruff: ignore[unconventional-import-alias]
from entitysdk import Client
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import EMCellMesh, EMDenseReconstructionDataset, MEModel
from morph_spines import MorphologyWithSpines, load_morphology_with_spines
from neurom.core import Morphology as NeuromMorphology
from voxcell import CellCollection

from obi_one.config import settings
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.map_em_synapses._defaults import default_node_spec_for
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    assemble_collection_from_specs,
)

L = logging.getLogger(__name__)


@dataclass(kw_only=True)
class ResolvedNeuron:
    """Result of resolving a neuron reference."""

    pt_root_id: int
    morph_entity: object
    morph_from_id: CellMorphologyFromID
    spiny_morph: MorphologyWithSpines
    smooth_morph: object  # neurom.core.Morphology
    source_mesh_entity: EMCellMesh
    source_dataset: EMDenseReconstructionDataset
    cave_version: int
    use_me_model: bool
    name_in_circuit: str
    phys_node_props: dict = field(default_factory=dict)
    fn_morph_h5: Path
    fn_morph_swc: Path


@dataclass(kw_only=True)
class ResolvedEMDataset:
    """Result of resolving the source EM dataset of multiple neurons.
    Ensures all neurons coming from the same dataset at the same version.
    """

    dataset_from_id_: EMDataSetFromID | None
    cave_version_: int | None

    @property
    def dataset_from_id(self) -> EMDataSetFromID | None:
        return self.dataset_from_id_

    @property
    def source_dataset_id(self) -> str | None:
        if self.dataset_from_id_ is None:
            err_str = "No EM dataset initialized yet!"
            raise ValueError(err_str)
        return self.dataset_from_id_.id_str

    @property
    def cave_version(self) -> int | None:
        return self.cave_version_

    @dataset_from_id.setter
    def dataset_from_id(self, new_val: EMDataSetFromID) -> None:
        if self.dataset_from_id_ is None:
            self.dataset_from_id_ = new_val
        elif new_val.id_str != self.source_dataset_id:
            err_str = "Input neurons originate from different EM datasets!"
            raise ValueError(err_str)

    @cave_version.setter
    def cave_version(self, new_val: int) -> None:
        if self.cave_version_ is None:
            self.cave_version_ = new_val
        elif new_val != self.cave_version_:
            err_str = "Input neurons from different release versions of the EM dataset!"
            raise ValueError(err_str)


def resolve_provenance(
    db_client: Client, morph_from_id: CellMorphologyFromID
) -> tuple[int, EMCellMesh, EMDenseReconstructionDataset]:
    source_mesh_entity = morph_from_id.source_mesh_entity(db_client=db_client)
    pt_root_id = source_mesh_entity.dense_reconstruction_cell_id
    source_dataset = db_client.get_entity(
        entity_id=source_mesh_entity.em_dense_reconstruction_dataset.id,  # ty:ignore[unresolved-attribute]
        entity_type=EMDenseReconstructionDataset,
    )
    return pt_root_id, source_mesh_entity, source_dataset


def ensure_mechanisms_placed(path_in: Path, path_out: Path) -> None:
    if not path_in.exists():
        err_str = f"Mechanisms directory {path_in} does not exist!"
        raise ValueError(err_str)
    path_out.mkdir(exist_ok=True)

    for mod_file in path_in.glob("*.mod"):
        shutil.copy(mod_file, path_out)


def resolve_list_neurons(  # ruff: ignore[too-many-locals]
    init_neurons: list[CellMorphologyFromID | MEModelFromID],
    db_client: Client,
    out_root: Path,
    spiny_dir: Path,
) -> tuple[list[ResolvedNeuron], ResolvedEMDataset, CellCollection, str | None]:

    lst_pt_root_ids = []
    lst_source_mesh_entity = []
    lst_morph_from_id = []
    lst_memodels = []
    resolved_em_dataset = ResolvedEMDataset(cave_version_=None, dataset_from_id_=None)
    cave_token = os.environ[settings.cave_client_config.microns_api_key]

    # First pass: resolve in entitycore
    for neuron_entry in init_neurons:
        use_me_model = isinstance(neuron_entry, MEModelFromID)
        if use_me_model:
            me_model_entity = neuron_entry.entity(db_client)
            morph_from_id = CellMorphologyFromID(id_str=str(me_model_entity.morphology.id))  # ty:ignore[unresolved-attribute]
        else:
            morph_from_id = neuron_entry
            me_model_entity = None
        lst_morph_from_id.append(morph_from_id)
        lst_memodels.append(me_model_entity)

        L.info("Resolving skeleton provenance...")
        pt_root_id, source_mesh_entity, source_dataset = resolve_provenance(
            db_client, morph_from_id
        )
        lst_pt_root_ids.append(pt_root_id)
        lst_source_mesh_entity.append(source_mesh_entity)
        em_dataset = EMDataSetFromID(id_str=str(source_dataset.id), auth_token=cave_token)
        resolved_em_dataset.dataset_from_id = em_dataset
        resolved_em_dataset.cave_version = source_mesh_entity.release_version

    em_dataset = resolved_em_dataset.dataset_from_id
    cave_version = resolved_em_dataset.cave_version
    if (em_dataset is None) or (cave_version is None):
        err_str = "Source EM dataset undetermined!"
        raise ValueError(err_str)

    # Second pass: resolve in CAVE
    L.info("Building node collections...")
    n_neurons = len(init_neurons)
    node_spec = default_node_spec_for(em_dataset, db_client)
    bio_pt_root_mapping = pandas.DataFrame(
        {"index": range(n_neurons)},
        index=pandas.Index(lst_pt_root_ids, name="pre_pt_root_id"),
    )
    coll_bio, _ = assemble_collection_from_specs(
        em_dataset, db_client, cave_version, node_spec, bio_pt_root_mapping
    )
    xyz_positions = coll_bio.positions
    if xyz_positions is None:
        xyz_positions = numpy.zeros((n_neurons, 3), dtype=float)

    # Third pass: Place files locally
    L.info("Placing neuron morphology files...")
    resolved_neurons: list[ResolvedNeuron] = []
    pt_root_id_names: dict[int, str] = {}
    mechanisms_placed = None
    for morph_from_id, me_model_entity, pt_root_id, source_mesh_entity, xyz in zip(
        lst_morph_from_id,
        lst_memodels,
        lst_pt_root_ids,
        lst_source_mesh_entity,
        xyz_positions,
        strict=True,
    ):
        L.info(f"...for neuron id: {pt_root_id}")
        resolved_neuron, mechanisms_placed_ = place_morphologies_and_mechanisms(
            morph_from_id=morph_from_id,
            me_model_entity=me_model_entity,  # ty:ignore[invalid-argument-type]
            source_mesh_entity=source_mesh_entity,
            source_dataset=source_dataset,
            pt_root_id=pt_root_id,
            xyz=xyz,
            db_client=db_client,
            out_root=out_root,
            spiny_morph_out_root=spiny_dir,
        )
        mechanisms_placed = mechanisms_placed or mechanisms_placed_
        if resolved_neuron.pt_root_id in pt_root_id_names:
            err_str = (
                f"Duplicate pt_root_id {resolved_neuron.pt_root_id}: "
                f"'{resolved_neuron.morph_entity.name or resolved_neuron.pt_root_id}' "  # ty:ignore[unresolved-attribute]
                f"resolves to the same physical neuron as "
                f"'{pt_root_id_names[resolved_neuron.pt_root_id]}'."
            )
            raise ValueError(err_str)
        resolved_neurons.append(resolved_neuron)
        pt_root_id_names[resolved_neuron.pt_root_id] = str(resolved_neuron.morph_entity.name)  # ty:ignore[unresolved-attribute]

    morph_names = [f"morphology/{rn.name_in_circuit}" for rn in resolved_neurons]
    coll_bio.properties["morphology"] = numpy.array(morph_names)
    return resolved_neurons, resolved_em_dataset, coll_bio, mechanisms_placed


def write_morphology_with_offset(
    morph: NeuromMorphology, offset: numpy.ndarray, fn_out: Path
) -> None:
    """Write morphology to file after applying an x/y/z offset to it."""
    mut = morph.to_morphio().as_mutable()
    soma_points = mut.soma.points
    if len(soma_points) > 0:
        mut.soma.points = soma_points + offset

    for section in mut.iter():
        section.points = section.points + offset  # ruff: ignore[non-augmented-assignment]

    mut.write(fn_out)


def place_morphologies_and_mechanisms(
    morph_from_id: CellMorphologyFromID,
    me_model_entity: MEModel | None,
    source_mesh_entity: EMCellMesh,
    source_dataset: EMDenseReconstructionDataset,
    pt_root_id: int,
    xyz: numpy.ndarray,
    db_client: Client,
    out_root: Path,
    spiny_morph_out_root: Path,
) -> tuple[ResolvedNeuron, str | None]:
    """Place neuron morphologies locally and return resolution of neuron in terms of provenance etc.

    Args:
        morph_from_id: A CellMorphologyFromID reference.
        me_model_entity: For input neurons that have emodels, a MEModel entity, else None.
        source_mesh_entity: A EMCellMesh entity that created the morph_from_id.
        source_dataset: The source EMDenseReconstructionDataset entity that created the neuron.
        pt_root_id: The id of the neuron within the CAVE version of the EM dataset.
        xyz: The x/y/z coordinates (in um) annotated in CAVE for the neuron.
        db_client: Entity SDK client.
        out_root: Root output directory for smooth morphology files and emodel hoc files,
        if applicable.
        spiny_morph_out_root: Root output directory for spiny morphology files.

    Returns:
        A ResolvedNeuron with all resolved information.
        A string that is the local (relative) path to a directory with emodel .mod files.
    """
    mechanisms_placed = None

    morph_entity = morph_from_id.entity(db_client)
    entity_id_str = str(morph_entity.id)
    # Place and load morphologies
    fn_morphology_out_swc = Path("morphologies/morphology") / (entity_id_str + ".swc")
    fn_morphology_out_h5 = Path("morphologies/morphology") / (entity_id_str + ".h5")
    fn_spiny_morph = Path(entity_id_str + ".h5")
    if (out_root / fn_morphology_out_swc).exists():
        err_str = (
            f"Duplicate entity in input: {entity_id_str}. "
            f"The same morphology cannot be chosen twice. "
            f"Please select different morphologies."
        )
        raise ValueError(err_str)

    smooth_morph = morph_from_id.neurom_morphology(db_client)
    write_morphology_with_offset(smooth_morph, -xyz, out_root / fn_morphology_out_swc)
    # For now: Spiny morphology not translated!
    morph_from_id.write_spiny_neuron_h5(spiny_morph_out_root / fn_spiny_morph, db_client=db_client)
    spiny_morph = load_morphology_with_spines(str(spiny_morph_out_root / fn_spiny_morph))
    write_morphology_with_offset(spiny_morph.morphology, -xyz, out_root / fn_morphology_out_h5)

    phys_node_props = {}
    if me_model_entity is not None:
        L.info("Placing mechanisms and .hoc file...")
        tmp_staging = out_root / f"temp_staging_{morph_entity.name}"
        memdl_paths = download_memodel(db_client, me_model_entity, str(tmp_staging))
        mechanisms_placed = "mod"
        ensure_mechanisms_placed(memdl_paths.mechanisms_dir, out_root / mechanisms_placed)
        hoc_dir = out_root / "hoc"
        hoc_dir.mkdir(parents=True)
        shutil.move(memdl_paths.hoc_path, hoc_dir)
        shutil.rmtree(tmp_staging)
        phys_node_props["model_template"] = numpy.array([f"hoc:{memdl_paths.hoc_path.stem}"])
        phys_node_props["model_type"] = numpy.array([0], dtype=numpy.int32)
        phys_node_props["morph_class"] = numpy.array([0], dtype=numpy.int32)
        if me_model_entity.calibration_result is not None:
            phys_node_props["@dynamics:threshold_current"] = numpy.array(
                [me_model_entity.calibration_result.threshold_current],
                dtype=numpy.float32,
            )
            phys_node_props["@dynamics:holding_current"] = numpy.array(
                [me_model_entity.calibration_result.holding_current],
                dtype=numpy.float32,
            )

    return ResolvedNeuron(
        pt_root_id=pt_root_id,
        morph_entity=morph_entity,
        morph_from_id=morph_from_id,
        spiny_morph=spiny_morph,
        smooth_morph=smooth_morph,
        source_mesh_entity=source_mesh_entity,
        source_dataset=source_dataset,
        name_in_circuit=entity_id_str,
        cave_version=source_mesh_entity.release_version,
        use_me_model=(me_model_entity is not None),
        phys_node_props=phys_node_props,
        fn_morph_h5=fn_spiny_morph,
        fn_morph_swc=fn_morphology_out_swc,
    ), mechanisms_placed
