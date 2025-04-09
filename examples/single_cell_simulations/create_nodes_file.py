import h5py
import numpy as np

# Create a new HDF5 file
with h5py.File('components/network/nodes.h5', 'w') as f:
    # Create the main nodes group
    nodes = f.create_group('nodes')
    
    # Create a population named "Node1" (instead of "biophysical_nodes")
    population = nodes.create_group('Node1')
    
    # Add node_type_id at the population level
    node_type_id = population.create_dataset('node_type_id', (1,), dtype='int64')
    node_type_id[0] = 1
    
    # Create the '0' group inside the population
    group_0 = population.create_group('0')
    
    # Create the '@library' group
    library = group_0.create_group('@library')
    
    # Add datasets to '@library'
    lib_model_type = library.create_dataset('model_type', (1,), dtype=h5py.special_dtype(vlen=str))
    lib_model_type[0] = "biophysical"
    
    lib_morph_class = library.create_dataset('morph_class', (1,), dtype=h5py.special_dtype(vlen=str))
    lib_morph_class[0] = "pyramidal"
    
    lib_region = library.create_dataset('region', (1,), dtype=h5py.special_dtype(vlen=str))
    lib_region[0] = "cortex"
    
    # Create the 'dynamics_params' group
    dynamics = group_0.create_group('dynamics_params')
    
    # Add datasets to 'dynamics_params'
    dynamics.create_dataset('AIS_scaler', (1,), dtype='float32', data=[1.0])
    dynamics.create_dataset('holding_current', (1,), dtype='float32', data=[0.0])
    dynamics.create_dataset('soma_scaler', (1,), dtype='float64', data=[1.0])
    dynamics.create_dataset('threshold_current', (1,), dtype='float32', data=[0.2])
    
    # Add all the datasets directly under group_0 (as shown in the screenshot)
    etype = group_0.create_dataset('etype', (1,), dtype=h5py.special_dtype(vlen=str))
    etype[0] = "cADpyr"
    
    hemisphere = group_0.create_dataset('hemisphere', (1,), dtype=h5py.special_dtype(vlen=str))
    hemisphere[0] = "right"
    
    layer = group_0.create_dataset('layer', (1,), dtype=h5py.special_dtype(vlen=str))
    layer[0] = "L5"
    
    minis = group_0.create_dataset('minis', (1,), dtype='float32')
    minis[0] = 0.0
    
    model_template = group_0.create_dataset('model_template', (1,), dtype=h5py.special_dtype(vlen=str))
    model_template[0] = "ctdb:my_template"
    
    model_type = group_0.create_dataset('model_type', (1,), dtype='uint32')
    model_type[0] = 1
    
    morph_class = group_0.create_dataset('morph_class', (1,), dtype='uint32')
    morph_class[0] = 1
    
    morphology = group_0.create_dataset('morphology', (1,), dtype=h5py.special_dtype(vlen=str))
    morphology[0] = "morphologies/neuron1.swc"
    
    mtype = group_0.create_dataset('mtype', (1,), dtype=h5py.special_dtype(vlen=str))
    mtype[0] = "L5_pyramidal"
    
    # Orientation datasets
    orientation_w = group_0.create_dataset('orientation_w', (1,), dtype='float64')
    orientation_w[0] = 1.0
    
    orientation_x = group_0.create_dataset('orientation_x', (1,), dtype='float64')
    orientation_x[0] = 0.0
    
    orientation_y = group_0.create_dataset('orientation_y', (1,), dtype='float64')
    orientation_y[0] = 0.0
    
    orientation_z = group_0.create_dataset('orientation_z', (1,), dtype='float64')
    orientation_z[0] = 0.0
    
    region = group_0.create_dataset('region', (1,), dtype='uint32')
    region[0] = 1
    
    synapse_class = group_0.create_dataset('synapse_class', (1,), dtype=h5py.special_dtype(vlen=str))
    synapse_class[0] = "EXC"
    
    # Position coordinates
    x = group_0.create_dataset('x', (1,), dtype='float32')
    x[0] = 0.0
    
    y = group_0.create_dataset('y', (1,), dtype='float32')
    y[0] = 0.0
    
    z = group_0.create_dataset('z', (1,), dtype='float32')
    z[0] = 0.0
    
    # Version information
    nodes.attrs['version'] = '1.0'

print("Successfully created nodes.h5 file with one neuron in Node1 population")
