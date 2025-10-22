from copy import deepcopy

DEFAULT_NODE_SPECS = {
    'Portion 65 of the IARPA MICrONS dataset':
    {
        "synapse_class": {
            "table": 'aibs_metamodel_mtypes_v661_v2',
            "column": 'classification_system',
            "default": "extrinsic_neuron"
        },
        "cell_type": {
            "table": 'aibs_metamodel_mtypes_v661_v2',
            "column": 'cell_type',
            "default": "extrinsic_neuron"
        },
        "volume": {
            "table": 'aibs_metamodel_mtypes_v661_v2',
            "column": 'volume',
            "default": -1
        },
        "status_axon": {
            "table": 'proofreading_status_and_strategy',
            "column": 'status_axon',
            "default": "unknown"
        },
        "status_dendrite": {
            "table": 'proofreading_status_and_strategy',
            "column": 'status_dendrite',
            "default": "unknown"
        },
        "__position": {
            "table": 'aibs_metamodel_mtypes_v661_v2',
            "column": "pt_position"
        }
    }
}

SYNAPTOME_SONATA_CONFIG = {
  "components": {
    "biophysical_neuron_models_dir": "",
    "mechanisms_dir": "",
    "morphologies_dir": "",
    "point_neuron_models_dir": "",
    "synaptic_models_dir": "",
    "templates_dir": ""
  },
  "networks": {
    "edges": [
      {
        "edges_file": "$BASE_DIR/",
        "populations": {
        }
      }
    ],
    "nodes": [
      {
        "nodes_file": "$BASE_DIR/",
        "populations": {
          node_population_post: {
            "alternate_morphologies": {
              "h5v1": "$BASE_DIR/" + fn_morphology_out_h5
            },
            "biophysical_neuron_models_dir": "$BASE_DIR/emodels_hoc",
            "morphologies_dir": "$BASE_DIR/morphologies",
            "type": "biophysical"
          }
        }
      },
      {
        "nodes_file": "$BASE_DIR/" + fn_nodes_out,
        "populations": {
          node_population_pre: {
            "type": "virtual"
          }
        }
      }
    ]
  },
  "node_sets_file": "$BASE_DIR/node_sets.json",
  "version": 2.3,
  "manifest": {
    "$BASE_DIR": "./"
  }
}

def default_node_spec_for(cave_client, em_dataset_entity):
    node_specs = DEFAULT_NODE_SPECS[em_dataset_entity.name].copy()

    info = cave_client._info.get_datastack_info()
    node_specs["__position"]["resolution"] = {
        "x": info["viewer_resolution_x"] * 1E-3,
        "y": info["viewer_resolution_y"] * 1E-3,
        "z": info["viewer_resolution_z"] * 1E-3
    }
    return node_specs

def sonata_config_for(fn_edges_out, fn_nodes_out, edge_population_name,
                      node_population_pre, node_population_post,
                      fn_morphology_out_h5):
    cfg = deepcopy(SYNAPTOME_SONATA_CONFIG)

    cfg["network"]["edges"]["edges_file"] += fn_edges_out
    cfg["network"]["edges"]["populations"][edge_population_name] = {
            "type": "chemical"
    }
    cfg["network"]["nodes"] = [
        {
            "nodes_file": "$BASE_DIR/" + fn_nodes_out,
            "populations": {
             node_population_post: {
                "alternate_morphologies": {
                "h5v1": "$BASE_DIR/" + fn_morphology_out_h5
                },
                "biophysical_neuron_models_dir": "$BASE_DIR/emodels_hoc",
                "morphologies_dir": "$BASE_DIR/morphologies",
                "type": "biophysical"
            }
            }
        },
        {
            "nodes_file": "$BASE_DIR/" + fn_nodes_out,
            "populations": {
            node_population_pre: {
                "type": "virtual"
            }
            }
        }
    ]
    return cfg
