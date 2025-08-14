import h5py
import numpy as np
import glob
from calculate_threshold_holding import get_threshold_and_holding_current

# get the hoc and morphology file paths
# use glob to get the hoc and morphology file paths

hoc_file = glob.glob("components/hocs/*.hoc")[0]
morph_file = glob.glob("components/morphologies/*.asc")[0]
EM_file = glob.glob("components/EM__*.json")[0]
# to find a better way to get this:
mtype = "L5TPC:A"

print("Hoc file:", hoc_file)
print("Morphology file:", morph_file)
print("EM file:", EM_file)

# Retrieve threshold and holding current
threshold_current, holding_current = get_threshold_and_holding_current(hoc_file, morph_file, EM_file)
print("Threshold current:", threshold_current)
print("Holding current:", holding_current)
# Define the path to the HDF5 file


# Create a new HDF5 file
with h5py.File('components/network/nodes.h5', 'w') as f:
    # Create the main nodes group
    nodes = f.create_group('nodes')
    # nodes.attrs['version'] = '1.0'

    # Create a population named "Node0"
    population = nodes.create_group('Node0')

    # Add node_type_id at the population level
    node_type_id = population.create_dataset('node_type_id', (1,), dtype='int64')
    node_type_id[0] = -1  # As per specification

    # Create the '0' group inside the population
    group_0 = population.create_group('0')

    # # Create the '@library' group with all fields shown in the first screenshot
    # library = group_0.create_group('@library')

    # # Add all datasets to '@library' as shown in first screenshot
    # lib_etype = library.create_dataset('etype', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_etype[0] = "cADpyr"

    # lib_layer = library.create_dataset('layer', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_layer[0] = "L5"

    # lib_model_type = library.create_dataset('model_type', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_model_type[0] = "biophysical"

    # lib_morph_class = library.create_dataset('morph_class', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_morph_class[0] = "PYR"

    # lib_mtype = library.create_dataset('mtype', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_mtype[0] = "L5TPC:A"

    # lib_population = library.create_dataset('population', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_population[0] = "Node0"

    # lib_region = library.create_dataset('region', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_region[0] = "cortex"

    # lib_synapse_class = library.create_dataset('synapse_class', (1,), dtype=h5py.special_dtype(vlen=str))
    # lib_synapse_class[0] = "EXC"
    # # Define all enum mappings
    # enum_mappings = {
    #     'etype': {'cADpyr': 0},
    #     'mtype': {'L5TPC:A': 0},
    #     'layer': {'L5': 0},  # Optional field
    #     'model_type': {'biophysical': 0},
    #     'morph_class': {'PYR': 0},
    #     'synapse_class': {'EXC': 0},
    #     'region': {'cortex': 0}  # Optional field
    # }

    # # Create enums and store values
    # for name, mapping in enum_mappings.items():
    #     # Create main enum dataset
    #     ds = group_0.create_dataset(name, (1,), dtype='int8')
    #     ds[0] = 0  # Set to first enum value

    #     # Store enum metadata
    #     ds.attrs.create('enum_values', list(mapping.keys()), dtype=h5py.string_dtype(encoding='utf-8'))
    #     ds.attrs.create('enum_indices', list(mapping.values()), dtype=np.int8)

    # Add mandatory dynamics_params fields
    dynamics = group_0.create_group('dynamics_params')
    dynamics.create_dataset('holding_current', (1,), dtype='float32', data=[holding_current])
    dynamics.create_dataset('threshold_current', (1,), dtype='float32', data=[threshold_current])

    # Add optional dynamics_params fields
    # dynamics.create_dataset('AIS_scaler', (1,), dtype='float32', data=[1.0])  # Example value
    # dynamics.create_dataset('input_resistance', (1,), dtype='float32', data=[150.0])  # Example value

    # Add standard string properties
    # model_template = group_0.create_dataset('model_template', (1,), dtype=h5py.special_dtype(vlen=str))
    model_template = group_0.create_dataset('model_template', (1,), dtype=h5py.string_dtype(encoding='utf-8'))
    model_template[0] = f"hoc:{hoc_file.split('/')[-1].split('.')[0]}"
    model_type = group_0.create_dataset('model_type', (1,), dtype='int32')
    model_type[0] = "0"
    morph_class = group_0.create_dataset('morph_class', (1,), dtype='int32')
    morph_class[0] = "0"

    # morphology = group_0.create_dataset('morphology', (1,), dtype=h5py.special_dtype(vlen=str))
    morphology = group_0.create_dataset('morphology', (1,), dtype=h5py.string_dtype(encoding='utf-8'))
    morphology[0] = f"morphologies/{morph_file.split('/')[-1].split('.')[0]}"
    mtype = group_0.create_dataset('mtype', (1,), dtype=h5py.string_dtype(encoding='utf-8'))
    mtype[0] = mtype #"L5TPC:A"

    # Add numeric properties
    numeric_props = {
        'x': 0.0,
        'y': 0.0,
        'z': 0.0,
        'rotation_angle_xaxis': 0.0,  # Optional field
        'rotation_angle_yaxis': 0.0,  # Optional field
        'rotation_angle_zaxis': 0.0,  # Optional field
        # 'exc-mini_frequency': 1.2,   # Example optional field value in Hz
        # 'inh-mini_frequency': 2.3,   # Example optional field value in Hz
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
        # 'hemisphere': "left",                # Example optional field value
        'morphology_producer': "biologic"   # Example optional field value
    }

    for name, value in optional_fields.items():
        ds = group_0.create_dataset(name, (1,), dtype=h5py.string_dtype(encoding='utf-8'))
        ds[0] = value

print("Successfully created nodes.h5 file")
