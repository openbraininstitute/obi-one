#!/bin/bash

# circuit simulation

# copy the ../data/tiny_circuits/N_10__top_nodes_dim6__asc/input folder to current directory
echo "Copying Spike replay input folder ../data/tiny_circuits/N_10__top_nodes_dim6__asc/input to current directory"
cp -r ../data/tiny_circuits/N_10__top_nodes_dim6__asc/input .

# Remove old compiled mod files
rm -r arm64/
# Compile mod files
# nrnivmodl N_10__top_nodes_dim6__asc/mod

# flag DISABLE_REPORTINGLIB to skip SonataReportHelper.mod and SonataReport.mod from compilation.
nrnivmodl -incflags "-DDISABLE_REPORTINGLIB" ../data/tiny_circuits/N_10__top_nodes_dim6__asc/mod

echo "Running circuit simulation"
simulation_config="../data/tiny_circuits/N_10__top_nodes_dim6__asc/simulation_config.json"

num_cores=4
mpiexec -n $num_cores python run_circuit_bluecellab.py --simulation_config $simulation_config --save-nwb