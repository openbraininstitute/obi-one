import numpy
import bluepysnap as snap
import copy
import os
import json
import h5py

def find_files(root, extension, exclude=[]):
    fns = os.listdir(root)
    out = []
    for fn in fns:
        if fn in exclude:
            continue
        _fn = os.path.join(root, fn)
        if os.path.isdir(_fn):
            if not os.path.islink(_fn): # Otherwise circular links cause trouble
                out = out + find_files(_fn, extension, exclude=exclude)
        elif os.path.splitext(_fn)[1] == extension:
            out.append(_fn)
    return out

def find_specified_nodes_and_edges(circ, node_delete_prefix, edge_delete_prefix):
    nodes_to_delete = []
    if node_delete_prefix is not None:
        for node in circ.nodes:
            if "virtual" in circ.nodes[node].property_values("model_type"):
                if node.startswith(node_delete_prefix):
                    nodes_to_delete.append(node)

    edges_to_delete = []
    for node in nodes_to_delete:
        edges_to_delete.extend(circ.nodes[node].source_in_edges())
    if edge_delete_prefix is not None: 
        for edge in circ.edges:
            if edge.startswith(edge_delete_prefix):
                edges_to_delete.append(edge)
    return nodes_to_delete, edges_to_delete

#FIXME: If brainbuilder can take the circuit as input instead of its path, this can be done in place.
def make_copy_with_deleted_nodes_edges(circ, node_delete_prefix, edge_delete_prefix):
    nodes_to_delete, edges_to_delete = find_specified_nodes_and_edges(circ, node_delete_prefix, edge_delete_prefix)
    circconfig = copy.deepcopy(circ.config)
    circconfig["networks"]["nodes"] = [_entry for _entry in circ.config["networks"]["nodes"] if not
                                        numpy.any([_pop in nodes_to_delete for
                                                _pop in _entry["populations"].keys()])
    ]
    circconfig["networks"]["edges"] = [_entry for _entry in circ.config["networks"]["edges"] if not
                                        numpy.any([_pop in edges_to_delete for
                                                _pop in _entry["populations"].keys()])
    ]
    circ_out_fn = circ._circuit_config_path + "_pruned.json"
    with open(circ_out_fn, "w") as fid:
        json.dump(circconfig, fid, indent=4)
    return circ_out_fn


def find_non_virtual_node_population(circ):
    non_virtual_population = [node for node in circ.nodes if circ.nodes[node].type != "virtual"]
    assert len(non_virtual_population) == 1
    non_virtual_population = non_virtual_population[0]
    return non_virtual_population


def preprocess(circ_path, node_delete_prefix, edge_delete_prefix):
    circ = snap.Circuit(circ_path)
    biophys_pop = find_non_virtual_node_population(circ)
    return make_copy_with_deleted_nodes_edges(circ, node_delete_prefix, edge_delete_prefix), biophys_pop


#FIXME: If this is done inside brainbuilder the files are known and don't have to be discovered
# Then all the assumptions below won't be needed.
def find_non_referenced_nodes_and_edges(circ_out):
    def find_files(root, extension, exclude=[]):
        fns = os.listdir(root)
        out = []
        for fn in fns:
            if fn in exclude:
                continue
            _fn = os.path.join(root, fn)
            if os.path.isdir(_fn):
                if not os.path.islink(_fn): # Otherwise circular links cause trouble
                    out = out + find_files(_fn, extension, exclude=exclude)
            elif os.path.splitext(_fn)[1] == extension:
                out.append(_fn)
        return out

    #FIXME: Assumed circuit file structure
    out_folder = os.path.split(circ_out._circuit_config_path)[0]

    #FIXME: Assumed morphologies directory
    found_h5s = [os.path.abspath(_x) for _x in find_files(out_folder, ".h5", "morphologies")]
    circ_h5s = ([os.path.abspath(node.h5_filepath) for node in circ_out.nodes.values()] + 
                [os.path.abspath(edge.h5_filepath) for edge in circ_out.edges.values()])


    missing_h5s = [_fn for _fn in found_h5s if _fn not in circ_h5s]

    #FIXME: Assumed naming pattern for nodes files
    missing_nodes = [_fn for _fn in missing_h5s if os.path.split(_fn)[1].startswith("nodes")]
    missing_edges = [_fn for _fn in missing_h5s if not os.path.split(_fn)[1].startswith("nodes")]

    #FIXME: More than one pair
    assert len(missing_nodes) == 1 and len(missing_edges) == 1
    missing_nodes = missing_nodes[0]
    missing_edges = missing_edges[0]
    return missing_nodes, missing_edges


def patch_edges_h5_file(missing_nodes, missing_edges):
    h5_node = h5py.File(missing_nodes, "r")
    h5_edge = h5py.File(missing_edges, "r+")

    missing_node_pop_name = list(h5_node["nodes"].keys())
    assert len(missing_node_pop_name) == 1
    missing_node_pop_name = missing_node_pop_name[0]

    missing_edge_pop_name = list(h5_edge["edges"].keys())
    assert len(missing_edge_pop_name) == 1
    missing_edge_pop_name = missing_edge_pop_name[0]

    h5_edge["edges"][missing_edge_pop_name]["source_node_id"].attrs["node_population"] = missing_node_pop_name
    h5_edge.close()
    h5_node.close()
    return missing_node_pop_name, missing_edge_pop_name

def patch_circuit(circ_out):
    missing_nodes, missing_edges = find_non_referenced_nodes_and_edges(circ_out)
    missing_node_pop_name, missing_edge_pop_name = patch_edges_h5_file(missing_nodes, missing_edges)

    circconfig = copy.deepcopy(circ_out.config)
    #FIXME: Assumed edge type. Take from parent instead.
    circconfig["networks"]["edges"].append(
        {
            "edges_file": missing_edges,
            "populations": {missing_edge_pop_name: {"type": "chemical"}}
        }
    )
    circconfig["networks"]["nodes"].append(
        {
            "nodes_file": missing_nodes,
            "populations": {missing_node_pop_name: {"type": "virtual"}}
        }
    )

    expected_mapping = os.path.join(
        os.path.split(circ_out._circuit_config_path)[0],
        "id_mapping.json"
        )
    assert os.path.isfile(expected_mapping)
    provenance = circconfig["components"].get("provenance", {})
    provenance["circuit_extraction"] = {"id_mapping": expected_mapping}
    circconfig["components"]["provenance"] = provenance

    with open(circ_out._circuit_config_path, "w") as fid:
        json.dump(circconfig, fid, indent=4)
    return circconfig, missing_node_pop_name
    

def patch_mapping(circconfig, missing_node_pop_name, non_virtual_population):
    #FIXME: Assumed circuit file structure
    fn = circconfig["components"]["provenance"]["circuit_extraction"]["id_mapping"]
    with open(fn, "r") as fid:
        mapping = json.load(fid)

    mapping[missing_node_pop_name]["old_node_population"] = non_virtual_population

    with open(fn, "w") as fid:
        json.dump(mapping, fid, indent=4)

def postprocess(circ_out, non_virtual_population):
    circcfg, missing_node_pop_name = patch_circuit(circ_out)
    patch_mapping(circcfg, missing_node_pop_name, non_virtual_population)

