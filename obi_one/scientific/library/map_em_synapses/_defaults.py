from copy import deepcopy

from entitysdk import Client

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID

DEFAULT_NODE_SPECS = {
    "Portion 65 of the IARPA MICrONS dataset": {
        "synapse_class": {
            "table": "aibs_metamodel_mtypes_v661_v2",
            "column": "classification_system",
            "default": "extrinsic_neuron",
        },
        "cell_type": {
            "table": "aibs_metamodel_mtypes_v661_v2",
            "column": "cell_type",
            "default": "extrinsic_neuron",
        },
        "volume": {"table": "aibs_metamodel_mtypes_v661_v2", "column": "volume", "default": -1},
        "status_axon": {
            "table": "proofreading_status_and_strategy",
            "column": "status_axon",
            "default": False,
        },
        "status_dendrite": {
            "table": "proofreading_status_and_strategy",
            "column": "status_dendrite",
            "default": False,
        },
        "__position": {"table": "aibs_metamodel_mtypes_v661_v2", "column": "pt_position"},
    }
}

SYNAPTOME_SONATA_CONFIG = {
    "components": {
        "biophysical_neuron_models_dir": "",
        "mechanisms_dir": "",
        "morphologies_dir": "",
        "point_neuron_models_dir": "",
        "synaptic_models_dir": "",
        "templates_dir": "",
    },
    "networks": {"edges": [], "nodes": []},
    "node_sets_file": "$BASE_DIR/node_sets.json",
    "version": 2.3,
    "manifest": {"$BASE_DIR": "./"},
}


def default_node_spec_for(em_dataset: EMDataSetFromID, db_client: Client) -> dict:
    node_specs = DEFAULT_NODE_SPECS[em_dataset._entity.name].copy()  # NOQA: SLF001

    resolution = em_dataset.viewer_resolution(db_client)
    node_specs["__position"]["resolution"] = {
        "x": resolution[0] * 1e-3,
        "y": resolution[1] * 1e-3,
        "z": resolution[2] * 1e-3,
    }
    return node_specs


def sonata_config_for(
    fn_edges_out: str,
    fn_nodes_out: str,
    edge_population_name: str,
    node_population_pre: str,
    node_population_post: str,
    fn_morphology_out_h5: str,
) -> dict:
    cfg = deepcopy(SYNAPTOME_SONATA_CONFIG)

    cfg["networks"]["edges"].extend(
        [
            {
                "edges_file": "$BASE_DIR/" + fn_edges_out,
                "populations": {edge_population_name: {"type": "chemical"}},
            }
        ]
    )
    cfg["networks"]["nodes"].extend(
        [
            {
                "nodes_file": "$BASE_DIR/" + fn_nodes_out,
                "populations": {
                    node_population_post: {
                        "alternate_morphologies": {"h5v1": "$BASE_DIR/" + fn_morphology_out_h5},
                        "biophysical_neuron_models_dir": "$BASE_DIR/hoc",
                        "morphologies_dir": "$BASE_DIR/morphologies",
                        "type": "biophysical",
                    }
                },
            },
            {
                "nodes_file": "$BASE_DIR/" + fn_nodes_out,
                "populations": {node_population_pre: {"type": "virtual"}},
            },
        ]
    )
    return cfg
