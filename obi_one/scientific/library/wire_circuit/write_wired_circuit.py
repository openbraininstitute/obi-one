import os
import json

from pathlib import Path
from entitysdk import Client, models
from conntility import ConnectivityMatrix

from .node_pop_from_matrix import create_cell_collection, COL_ME_MODEL_ID_
from .place_files import place_all_hoc_files, place_all_morphologies
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import write_edges

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
    
    nodes_dict["populations"][node_pop_name].update(
        place_all_morphologies(
            memodels, client, circuit_root
        )
    )
    nodes_dict["populations"][node_pop_name].update(
        place_all_hoc_files(
            memodels, client, circuit_root
        )
    )
    cfg["networks"]["nodes"].append(nodes_dict)
    
    os.makedirs(str(circuit_root / "intrinsic_connections"), exist_ok=True)
    write_edges(
        circuit_root / "intrinsic_connections" / "edges.h5",
        edge_pop_name,
        M._edge_indices.rename(columns={"row": "pre_node_id", "col": "post_node_id"}),
        M.edges,
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
    with open(circuit_root / "config.json", "w") as fid:
        json.dump(cfg, fid, indend=2)

