from copy import deepcopy

from entitysdk import Client

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.library.map_em_synapses.constants import (
    DEFAULT_NODE_SPECS,
    SYNAPTOME_SONATA_CONFIG,
)


def default_node_spec_for(em_dataset: EMDataSetFromID, db_client: Client) -> dict:
    resolution = em_dataset.viewer_resolution(db_client)
    em_name = str(em_dataset.entity(db_client=db_client).name)
    node_specs = DEFAULT_NODE_SPECS[em_name].copy()
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
    mechanisms_dir: str | None = None,
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
        mechanisms_dir: [Optional] Changes the entry of components/mechanisms_dir
            from "" to this (prepending $BASE_DIR).
    """
    cfg = deepcopy(SYNAPTOME_SONATA_CONFIG)

    if mechanisms_dir is not None:
        cfg["components"]["mechanisms_dir"] = "$BASE_DIR/" + mechanisms_dir  # ty:ignore[invalid-assignment]
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
        bio_props["alternate_morphologies"] = {"h5v1": "$BASE_DIR/" + alternate_morphologies_h5}
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
