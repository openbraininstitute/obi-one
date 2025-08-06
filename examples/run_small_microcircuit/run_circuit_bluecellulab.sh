#!/bin/bash

# circuit simulation

# Remove old compiled mod files
rm -r arm64/
# Compile mod files
# flag DISABLE_REPORTINGLIB to skip SonataReportHelper.mod and SonataReport.mod from compilation.
nrnivmodl -incflags "-DDISABLE_REPORTINGLIB" <PATH_TO_MOD_FILES>  # Replace with the actual path to your mod files

echo "Running circuit simulation"
simulation_config="<PATH_TO_SIMULATION_CONFIG_FILE>"  # Replace with the actual path to your simulation config file

num_cores=4
mpiexec -n $num_cores python run_circuit_bluecellab.py --simulation_config $simulation_config --save-nwb