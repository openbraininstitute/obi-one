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
    node_specs = DEFAULT_NODE_SPECS[em_dataset._entity.name].copy()  # NOQA: SLF001  # ty:ignore[invalid-argument-type, unresolved-attribute]

    resolution = em_dataset.viewer_resolution(db_client)
    node_specs["__position"]["resolution"] = {
        "x": resolution[0] * 1e-3,
        "y": resolution[1] * 1e-3,
        "z": resolution[2] * 1e-3,
    }  # ty:ignore[invalid-assignment]
    return node_specs


def sonata_config_for(
    fn_edges_out: str,
    fn_nodes_out: str,
    edge_populations: dict[str, dict],
    biophysical_population: str,
    virtual_population: str | None = None,
    morphologies_dir: str = "morphologies",
    alternate_morphologies_h5: str | None = None,
) -> dict:
    """Build a SONATA circuit_config.json.

    Works for both single-neuron and multi-neuron synaptome circuits.

    Args:
        fn_edges_out: Edge HDF5 filename (relative path)
        fn_nodes_out: Node HDF5 filename (relative path)
        edge_populations: Dictionary with {edge population name: properties dict}
            (example: {"afferent_synapses": {"type": "chemical"}})
        biophysical_population: Name of the biophysical node population
        virtual_population: [Optional] Name of the virtual node population
        morphologies_dir: Directory containing morphology files
        alternate_morphologies_h5: [Optional] Adds an 'alternate_morphologies'
            entry pointing to this H5 path (mostly for single-neuron spiny case).
    """
    cfg = deepcopy(SYNAPTOME_SONATA_CONFIG)

    # Edge populations
    if edge_populations:
        cfg["networks"]["edges"].append(  # ty:ignore[invalid-argument-type, not-subscriptable, unresolved-attribute]
            {"edges_file": "$BASE_DIR/" + fn_edges_out, "populations": edge_populations}
        )

    # Biophysical node population
    bio_props = {
        "biophysical_neuron_models_dir": "$BASE_DIR/hoc",
        "morphologies_dir": "$BASE_DIR/" + morphologies_dir,
        "type": "biophysical",
    }
    if alternate_morphologies_h5 is not None:
        bio_props["alternate_morphologies"] = {"h5v1": "$BASE_DIR/" + alternate_morphologies_h5}  # ty:ignore[invalid-assignment]
    cfg["networks"]["nodes"].append(  # ty:ignore[invalid-argument-type, not-subscriptable, unresolved-attribute]
        {
            "nodes_file": "$BASE_DIR/" + fn_nodes_out,
            "populations": {biophysical_population: bio_props},
        }
    )

    # Virtual node population
    if virtual_population is not None:
        cfg["networks"]["nodes"].append(  # ty:ignore[invalid-argument-type, not-subscriptable, unresolved-attribute]
            {
                "nodes_file": "$BASE_DIR/" + fn_nodes_out,
                "populations": {virtual_population: {"type": "virtual"}},
            }
        )

    return cfg
