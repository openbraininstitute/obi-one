#!/bin/bash

# 10 circuit simulation
# Remove old compiled mod files. For linux, use "rm -r x86_64/"
rm -r arm64/
# Compile mod files
nrnivmodl ../data/tiny_circuits/N_10__top_nodes_dim6__asc/mod

echo "Running 10 cells circuit simulation"
simulation_config="../data/tiny_circuits/N_10__top_nodes_dim6__asc/simulation_config.json"
population_name="S1nonbarrel_neurons" # Optional: Set the node population name. Default: "S1nonbarrel_neurons"
gid=0 # Optional: Set the cell GID. Default: 0
num_cores=4
num_cells=10

# mpiexec -n $num_cores python backup_run10cells_parallel.py --config $simulation_config --node $nodes --start_gid $gid --num_cells $num_cells
mpiexec -n $num_cores python run_circuit_bluecellulab.py --config $simulation_config --population_name $population_name --start_gid $gid --num_cells $num_cells