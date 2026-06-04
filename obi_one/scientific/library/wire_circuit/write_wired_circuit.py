import os
import json
import neurom
import pandas
import numpy

from pathlib import Path
from entitysdk import Client, models
from conntility import ConnectivityMatrix
from conntility.subcellular import MorphologyPathDistanceCalculator

from .node_pop_from_matrix import create_cell_collection, COL_ME_MODEL_ID_
from .place_files import place_all_hoc_files, place_all_morphologies
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import write_edges

SYNAPSE_LOCATION_DEFAULTS = {
    str(neurom.APICAL_DENDRITE): 1.0,
    str(neurom.BASAL_DENDRITE): 1.0,
    str(neurom.AXON): 0.0,
    "exponential_scale": 0.0
}


def segments_dataframe_for(morphology_filename: Path) -> pandas.DataFrame:
    m = neurom.load_morphology(morphology_filename)
    pd = MorphologyPathDistanceCalculator(m._morphio_morph)

    segment_dict = {}
    for sec in m.sections:
        for i, seg in enumerate(sec.segments):
            l = numpy.linalg.norm(seg[1] - seg[0])
            segment_dict.setdefault("afferent_section_id", []).append(sec.id + 1)
            segment_dict.setdefault("afferent_segment_id", []).append(i)
            segment_dict.setdefault("afferent_section_type", []).append(str(sec.type))
            segment_dict.setdefault("segment_length", []).append(l)
    segments = pandas.DataFrame(segment_dict)
    segments["afferent_segment_offset"] = 0.0

    soma = pandas.DataFrame({
        "afferent_section_id": [0],
        "afferent_segment_id": [0],
        "afferent_segment_offset": [0]
    })
    segments["soma_path_distances"] = pd.path_distances(soma, segments)[0]
    return segments


def create_morphology_locations(specs_df: pandas.DataFrame, segments: pandas.DataFrame):
    picked_indices = []
    for _, row in specs_df.iterrows():
        p = numpy.exp(segments["soma_path_distances"] * -numpy.abs(row["exponential_scale"])).to_numpy()
        if row["exponential_scale"] < 0:
            p = 1.0 - p
        p *= segments["segment_length"].to_numpy()
        p *= row[segments["afferent_section_type"]].astype(float).to_numpy()
        picked_indices.append(numpy.random.choice(segments.index, p=p/numpy.nansum(p)))
    picked = segments.loc[picked_indices, ["afferent_section_id", "afferent_segment_id", "afferent_section_type"]]
    picked["afferent_segment_offset"] = numpy.random.rand(len(picked)) * segments.loc[picked_indices, "segment_length"]
    picked.index = specs_df.index
    return picked


def structural_edge_properties(M: ConnectivityMatrix,
                               morph_file_dict: dict[str, tuple[Path | None, Path | None]]):
    pre_post_morphs = M.edge_associated_vertex_properties(COL_ME_MODEL_ID_)
    edges = M.edges.copy()
    for k, v in SYNAPSE_LOCATION_DEFAULTS.items():
        if k not in edges.columns:
            edges[k] = v

    return pandas.concat(
        [
            create_morphology_locations(
                edges[pre_post_morphs["col"] == me_mdl_id],
                segments_dataframe_for(Path(morphology_file[1]))
            )
        for me_mdl_id, morphology_file in morph_file_dict.items()
        if morphology_file[1] is not None
        ], axis=0).sort_index()


def write_wired_circuit(
        M: ConnectivityMatrix,
        client: Client,
        circuit_root: Path,
        node_pop_name: str = "default",
        edge_pop_name: str = "default"
    ):
    if COL_ME_MODEL_ID_ not in M.vertex_properties:
        raise ValueError("Input ConnectivityMatrix does not specify MEModel ids!")
    
    cfg = {
        "components": {},
        "networks": {
            "edges": [],
            "nodes": []
        },
        "version": 2.3,
        "manifest": {
            "$BASE_DIR": "./"
        }
    }

    memodel_ids = M.vertices[COL_ME_MODEL_ID_].to_numpy()
    memodels = {
        id_str: client.get_entity(entity_id=id_str, entity_type=models.MEModel)
        for id_str in memodel_ids
    }

    coll = create_cell_collection(
        M, client, node_pop_name
    )
    os.makedirs(str(circuit_root / "intrinsic_neurons"), exist_ok=True)
    coll.save_sonata(str(circuit_root / "intrinsic_neurons" / "nodes.h5"))
    nodes_dict = {
        "nodes_file": "$BASE_DIR/intrinsic_neurons/nodes.h5",
        "populations": {
            node_pop_name: {
                "type": "biophysical"
            }
        }
    }
    
    config_update, morph_file_dict = place_all_morphologies(
        memodels, client, circuit_root
    )
    nodes_dict["populations"][node_pop_name].update(
        config_update
    )
    nodes_dict["populations"][node_pop_name].update(
        place_all_hoc_files(
            memodels, client, circuit_root
        )
    )
    cfg["networks"]["nodes"].append(nodes_dict)
    
    os.makedirs(str(circuit_root / "intrinsic_connections"), exist_ok=True)
    structural_props = structural_edge_properties(M, morph_file_dict)
    assert (structural_props.index == M._edges.index).all()
    relevant_cols = ["afferent_section_id", "afferent_segment_id", "afferent_section_type", "afferent_segment_offset"]
    write_edges(
        circuit_root / "intrinsic_connections" / "edges.h5",
        edge_pop_name,
        M._edge_indices.rename(columns={"row": "pre_node_id", "col": "post_node_id"}),
        pandas.concat([M.edges, structural_props], axis=1)[relevant_cols],
        node_pop_name,
        node_pop_name
    )
    edges_dict = {
        "edges_file": "$BASE_DIR/intrinsic_connections/edges.h5",
        "populations": {
            edge_pop_name: {"type": "chemical"}
        }
    }
    cfg["networks"]["edges"].append(edges_dict)
    with open(circuit_root / "circuit_config.json", "w") as fid:
        json.dump(cfg, fid, indent=2)

