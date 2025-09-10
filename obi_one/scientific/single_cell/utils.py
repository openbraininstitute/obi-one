import json
import os
import shutil
from pathlib import Path
from obi_one.scientific.utils.neuron_set_utils import create_nodes_file
import h5py

from pathlib import Path
import shutil

def memodel_to_sonata_single_cell(memodel_path, sonata_path, mtype, threshold_current, holding_current):
    """
    Convert a downloaded MEModel folder to a SONATA single cell circuit structure.

    Args:
        memodel_path (str or Path): Path to the downloaded MEModel folder.
        sonata_path (str or Path): Path to the output 'sonata' folder.
        mtype (str): Cell mtype.
        threshold_current (float): Threshold current.
        holding_current (float): Holding current.
    """
    memodel_path = Path(memodel_path)
    sonata_path = Path(sonata_path)

    # Prepare subdirectories
    subdirs = {
        "hocs": sonata_path / "hocs",
        "mechanisms": sonata_path / "mechanisms",
        "morphologies": sonata_path / "morphologies",
        "network": sonata_path / "network",
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)

    # Copy hoc file
    hoc_file = next((memodel_path / "hoc").glob("*.hoc"))
    hoc_dst = subdirs["hocs"] / hoc_file.name
    if hoc_file.resolve() != hoc_dst.resolve():
        shutil.copy(hoc_file, hoc_dst)

    # Copy morphology file
    morph_file = next((memodel_path / "morphology").glob("*.asc"))
    morph_dst = subdirs["morphologies"] / morph_file.name
    if morph_file.resolve() != morph_dst.resolve():
        shutil.copy(morph_file, morph_dst)

    # Copy mechanisms
    mech_src = memodel_path / "mechanisms"
    mech_dst = subdirs["mechanisms"]
    for file in mech_src.iterdir():
        if file.is_file():
            target = mech_dst / file.name
            if file.resolve() != target.resolve():
                shutil.copy(file, target)

    # Create SONATA network files
    create_nodes_file(
        hoc_file=str(hoc_dst),
        morph_file=str(morph_dst),
        output_path=str(subdirs["network"]),
        mtype=mtype,
        threshold_current=threshold_current,
        holding_current=holding_current,
    )

    create_circuit_config(output_path=sonata_path)
    create_node_sets_file(output_path=sonata_path)

    print(f"SONATA single cell circuit created at {sonata_path}")
    return sonata_path


def create_nodes_file(hoc_file, morph_file, output_path, mtype, threshold_current, holding_current):
    """
    Create a SONATA nodes.h5 file for a single cell population.
    Args:
        hoc_file (str): Path to the hoc file.
        morph_file (str): Path to the morphology file.
        output_path (str): Directory where nodes.h5 will be written.
        mtype (str): Cell mtype (e.g., 'L5TPC:A').
        threshold_current (float): Threshold current value.
        holding_current (float): Holding current value.
    """
    os.makedirs(output_path, exist_ok=True)
    nodes_h5_path = os.path.join(output_path, 'nodes.h5')

    with h5py.File(nodes_h5_path, 'w') as f:
        nodes = f.create_group('nodes')
        population = nodes.create_group('All')
        node_type_id = population.create_dataset('node_type_id', (1,), dtype='int64')
        node_type_id[0] = -1
        group_0 = population.create_group('0')

        # Add mandatory dynamics_params fields
        dynamics = group_0.create_group('dynamics_params')
        dynamics.create_dataset('holding_current', (1,), dtype='float32', data=[holding_current])
        dynamics.create_dataset('threshold_current', (1,), dtype='float32', data=[threshold_current])

        # Add standard string properties
        model_template = group_0.create_dataset('model_template', (1,), dtype=h5py.string_dtype(encoding='utf-8'))
        model_template[0] = f"hoc:{os.path.splitext(os.path.basename(hoc_file))[0]}"
        model_type = group_0.create_dataset('model_type', (1,), dtype='int32')
        model_type[0] = 0
        morph_class = group_0.create_dataset('morph_class', (1,), dtype='int32')
        morph_class[0] = 0
        morphology = group_0.create_dataset('morphology', (1,), dtype=h5py.string_dtype(encoding='utf-8'))
        morphology[0] = f"morphologies/{os.path.splitext(os.path.basename(morph_file))[0]}"
        mtype_ds = group_0.create_dataset('mtype', (1,), dtype=h5py.string_dtype(encoding='utf-8'))
        mtype_ds[0] = mtype

        # Add numeric properties
        numeric_props = {
            'x': 0.0,
            'y': 0.0,
            'z': 0.0,
            'rotation_angle_xaxis': 0.0,
            'rotation_angle_yaxis': 0.0,
            'rotation_angle_zaxis': 0.0,
        }
        for name, value in numeric_props.items():
            ds = group_0.create_dataset(name, (1,), dtype='float32')
            ds[0] = value

        # Add quaternion-based orientation (mandatory)
        orientation_props = {
            'orientation_w': 1.0,
            'orientation_x': 0.0,
            'orientation_y': 0.0,
            'orientation_z': 0.0,
        }
        for name, value in orientation_props.items():
            ds = group_0.create_dataset(name, (1,), dtype='float64')
            ds[0] = value

        # Add optional fields with default or placeholder values
        optional_fields = {
            'morphology_producer': "biologic"
        }
        for name, value in optional_fields.items():
            ds = group_0.create_dataset(name, (1,), dtype=h5py.string_dtype(encoding='utf-8'))
            ds[0] = value

    print(f"Successfully created nodes.h5 file at {nodes_h5_path}")


def create_circuit_config(output_path, node_population_name="All"):
    """
    Create a minimal SONATA circuit_config.json for a single cell or small circuit.
    Args:
        output_path (str): Directory where circuit_config.json will be written.
        node_population_name (str): Name of the node population (default: 'All').
    """
    config = {
        "manifest": {
            "$BASE_DIR": ".",
            "$COMPONENT_DIR": ".",
            "$NETWORK_DIR": "$BASE_DIR/network"
        },
        "components": {
            "morphologies_dir": "$COMPONENT_DIR/morphologies",
            "biophysical_neuron_models_dir": "$COMPONENT_DIR/hocs"
        },
        "node_sets_file": "$BASE_DIR/node_sets.json",
        "networks": {
            "nodes": [
                {
                    "nodes_file": "$NETWORK_DIR/nodes.h5",
                    "populations": {
                        node_population_name: {
                            "type": "biophysical",
                            "morphologies_dir": "$COMPONENT_DIR/",
                            "alternate_morphologies": {
                                "neurolucida-asc": "$COMPONENT_DIR/"
                            }
                        }
                    }
                }
            ],
            "edges": []
        }
    }
    os.makedirs(output_path, exist_ok=True)
    config_path = os.path.join(output_path, "circuit_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Successfully created circuit_config.json at {config_path}")



def create_node_sets_file(output_path, node_population_name="All", node_set_name="All", node_id=0):
    """
    Create a minimal node_sets.json file for a single cell or small circuit.
    Args:
        output_path (str): Directory where node_sets.json will be written.
        node_population_name (str): Name of the node population (default: 'All').
        node_set_name (str): Name of the node set (default: 'All').
        node_id (int): Node ID to include (default: 0).
    """
    node_sets = {
        node_set_name: {
            "population": node_population_name,
            "node_id": [node_id]
        }
    }
    os.makedirs(output_path, exist_ok=True)
    node_sets_path = os.path.join(output_path, "node_sets.json")
    with open(node_sets_path, "w") as f:
        json.dump(node_sets, f, indent=2)
    print(f"Successfully created node_sets.json at {node_sets_path}")
